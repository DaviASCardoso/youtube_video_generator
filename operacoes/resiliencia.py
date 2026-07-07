"""Motor de resposta a falhas — classificação de erros.

Coração do Pilar 6: em vez de "retry N vezes com backoff", o motor primeiro
**classifica** o erro e depois casa a resposta à classe, porque falhas diferentes
pedem reações opostas. Este arquivo cobre a classificação; o backoff, o circuito e o
policy-engine `executar` crescem sobre ele (mesmo módulo).

Classes (fonte da verdade em `operacoes.configuracao.CLASSES_ERRO`):
- **transitorio** — timeout, conexão caída, 5xx, rate-limit 429. A única classe de
  fato retryável.
- **permanente** — 4xx que não é auth/quota, input malformado, validação. Retry só
  gasta tempo/dinheiro: falhar rápido e registrar.
- **auth** — 401/403, credencial expirada/inválida (o caso do refresh-token de 7 dias).
  Repetir a mesma chamada é inútil: tentar refresh, senão halt do destino + escalar.
- **quota** — 429 de quota ou um cap do próprio pilar (orçamento/cota). Não spammar
  retry: **deferir** para a janela em que o recurso reseta e escalar.
- **recurso** — disco/NAS cheio, memória. Retry não ajuda até liberar: halt + escalar.

A classificação é por **duck-typing** (status HTTP e nomes de tipo/módulo), sem
importar os SDKs (Groq/Together/Google/urllib) — assim o motor é leve e testável com
exceções sintéticas. Erro desconhecido cai em `transitorio` (o comportamento de hoje,
que já retenta tudo), a menos que se pareça com validação (então `permanente`).
"""

import errno
import random
import time

from operacoes.circuitos import ABERTO, MEIO_ABERTO, circuitos
from operacoes.configuracao import mesclar_operacao

# Classes de erro (== operacoes.configuracao.CLASSES_ERRO).
TRANSITORIO = "transitorio"
PERMANENTE = "permanente"
AUTH = "auth"
QUOTA = "quota"
RECURSO = "recurso"

# errnos de "recurso esgotado" (disco/quota de FS cheios).
_ERRNOS_RECURSO = {errno.ENOSPC, errno.EDQUOT, errno.EFBIG}

# Palavras que, num 429, indicam quota/billing (defer) em vez de rate-limit (retry).
_PISTAS_QUOTA = (
    "quota", "exceeded", "insufficient", "billing", "dailylimit", "daily limit",
    "resource_exhausted", "resourceexhausted", "out of credits", "insufficient_quota",
)

# Nomes de exceção que sinalizam cada classe quando não há status HTTP.
_PISTAS_AUTH = ("auth", "credential", "unauthorized", "forbidden", "refresh", "token", "permission")
_PISTAS_TRANSITORIO = ("timeout", "timedout", "connection", "connectionreset", "ratelimit", "rate limit", "temporarily", "unavailable", "econnreset", "read timed out")
_PISTAS_PERMANENTE = ("validation", "invalid", "malformed", "notfound", "not found", "badrequest", "bad request", "decodeerror", "value error")


def _status(erro) -> int | None:
    """Extrai um status HTTP do erro, cobrindo os formatos dos vários clientes."""
    for attr in ("status_code", "status", "code"):
        v = getattr(erro, attr, None)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    resp = getattr(erro, "response", None)
    if resp is None:
        resp = getattr(erro, "resp", None)
    if resp is not None:
        for attr in ("status_code", "status", "code"):
            v = getattr(resp, attr, None)
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isdigit():
                return int(v)
        try:  # httplib2.Response é um dict com 'status' (googleapiclient.HttpError)
            s = resp.get("status")
            if s is not None:
                return int(s)
        except (AttributeError, TypeError, ValueError):
            pass
    return None


def _texto(erro) -> str:
    return f"{type(erro).__name__} {erro}".lower()


def _tem_pista(texto: str, pistas) -> bool:
    return any(p in texto for p in pistas)


def classificar(erro: BaseException) -> str:
    """Classifica um erro numa das classes (transitorio/permanente/auth/quota/recurso)."""
    # 1. Classes que o projeto conhece pelo tipo.
    from geracao.pipeline import OrcamentoExcedido

    if isinstance(erro, OrcamentoExcedido):
        return QUOTA
    if isinstance(erro, MemoryError):
        return RECURSO
    if isinstance(erro, (TimeoutError,)):
        return TRANSITORIO
    if isinstance(erro, ConnectionError):
        return TRANSITORIO
    if isinstance(erro, OSError) and erro.errno in _ERRNOS_RECURSO:
        return RECURSO

    texto = _texto(erro)

    # 2. Por status HTTP, quando há um.
    status = _status(erro)
    if status is not None:
        if status in (401, 403):
            return AUTH
        if status == 429:
            return QUOTA if _tem_pista(texto, _PISTAS_QUOTA) else TRANSITORIO
        if status == 408 or status >= 500:
            return TRANSITORIO
        if 400 <= status < 500:
            return PERMANENTE

    # 3. Sem status: por pistas no nome/mensagem.
    if _tem_pista(texto, _PISTAS_QUOTA):
        return QUOTA
    if _tem_pista(texto, _PISTAS_AUTH):
        return AUTH
    if _tem_pista(texto, _PISTAS_TRANSITORIO):
        return TRANSITORIO
    if isinstance(erro, (ValueError, KeyError, TypeError)) or _tem_pista(texto, _PISTAS_PERMANENTE):
        return PERMANENTE

    # 4. Desconhecido: transitório (o posture de hoje, que retenta tudo).
    return TRANSITORIO


def _headers(erro):
    """Headers do erro/response, num dict-like, ou None."""
    for obj in (erro, getattr(erro, "response", None), getattr(erro, "resp", None)):
        if obj is None:
            continue
        h = getattr(obj, "headers", None)
        if h is not None:
            return h
        if isinstance(obj, dict):  # httplib2.Response
            return obj
    return None


def retry_after(erro: BaseException) -> float | None:
    """Segundos do header `Retry-After`, quando a API o envia (senão None).

    Suporta o formato de segundos inteiros (o comum em 429/503). Datas HTTP são
    ignoradas (devolve None) — o backoff normal assume."""
    headers = _headers(erro)
    if headers is None:
        return None
    valor = None
    try:
        # dict-like case-insensitive? tenta as variações comuns.
        for chave in ("Retry-After", "retry-after", "RETRY-AFTER"):
            if chave in headers:
                valor = headers[chave]
                break
        if valor is None and hasattr(headers, "get"):
            valor = headers.get("Retry-After") or headers.get("retry-after")
    except (TypeError, AttributeError):
        return None
    if valor is None:
        return None
    try:
        segundos = float(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return segundos if segundos >= 0 else None


# --- Política e backoff -----------------------------------------------------


class PoliticaFalhas:
    """Vista tipada do bloco `operacao` (mesclado) — os knobs que o motor consulta."""

    def __init__(self, cfg: dict | None = None):
        cfg = mesclar_operacao(cfg)
        self.caps = cfg["caps_por_estagio"]
        self.base = cfg["backoff"]["base_seg"]
        self.teto = cfg["backoff"]["teto_seg"]
        self.jitter = cfg["backoff"]["jitter"]
        self.circuito = cfg["circuito"]
        self.failover = bool(cfg["failover"])
        self.falha_parcial = cfg["falha_parcial"]
        self.defer_horas = cfg["defer_horas"]

    def cap(self, estagio: str) -> int:
        """Nº máximo de tentativas (classe transitória) para um estágio."""
        return int(self.caps.get(estagio, 3))


def de_tipo(tipo) -> PoliticaFalhas:
    """Constrói a política a partir do bloco `operacao` de um tipo."""
    return PoliticaFalhas(tipo.config.get_all().get("operacao"))


def proxima_espera(tentativa: int, politica: PoliticaFalhas, retry_after_seg=None, _rng=random) -> float:
    """Segundos a esperar antes da próxima tentativa.

    Honra o `Retry-After` do servidor quando presente (sem chute, sem jitter — o
    servidor já deconflita). Senão, backoff exponencial `base·2^tentativa`, limitado
    ao teto, com jitter (fração ±) para os retries não sincronizarem num rebanho.
    """
    if retry_after_seg is not None:
        return max(0.0, float(retry_after_seg))

    espera = politica.base * (2 ** tentativa)
    espera = min(espera, politica.teto)
    if politica.jitter > 0:
        delta = espera * politica.jitter * (_rng.random() * 2 - 1)
        espera = max(0.0, espera + delta)
    return min(espera, politica.teto)


# --- Exceções tipadas que sobem para a orquestração -------------------------


class Deferir(Exception):
    """Quota/orçamento estourou: reprogramar o job para quando o recurso reseta."""

    def __init__(self, classe: str, quando_horas: float, contexto: dict | None = None):
        self.classe = classe
        self.quando_horas = quando_horas
        self.contexto = contexto or {}
        super().__init__(f"deferido ({classe}) por {quando_horas}h: {self.contexto}")


class HaltDestino(Exception):
    """Auth sem refresh possível: halt daquele destino e escalar."""

    def __init__(self, contexto: dict | None = None, causa: BaseException | None = None):
        self.contexto = contexto or {}
        self.causa = causa
        super().__init__(f"halt do destino (auth): {self.contexto}")


class ResilienciaEsgotada(Exception):
    """As estratégias casadas se esgotaram: dead-letter (nunca perdido em silêncio)."""

    def __init__(self, classe: str, contexto: dict | None = None, causa: BaseException | None = None):
        self.classe = classe
        self.contexto = contexto or {}
        self.causa = causa
        super().__init__(f"resiliência esgotada ({classe}): {self.contexto}")


# --- Policy-engine ----------------------------------------------------------


def executar(
    fn,
    *,
    estagio: str,
    provedor: str,
    politica: PoliticaFalhas,
    custo_ok=None,
    alternativa=None,
    refresh=None,
    contexto: dict | None = None,
    relatorio: dict | None = None,
    dormir=None,
    _rng=random,
    _circuitos=None,
):
    """Roda `fn()` casando a resposta à classe do erro (o coração do pilar).

    - **transitório**: retenta até o teto do estágio (backoff honrado+jitter), sem furar
      o orçamento (`custo_ok`); esgotado → failover para `alternativa` ou dead-letter.
    - **permanente/recurso**: falha rápido (não retenta, não abre circuito).
    - **auth**: tenta `refresh()` uma vez; senão `HaltDestino`.
    - **quota/orçamento**: `Deferir` para a janela em que o recurso reseta.
    - **circuito aberto** do provedor: pula direto para o failover (não martela um
      serviço morto); **meio-aberto**: um único probe.

    Args:
        fn: uma tentativa da chamada externa (`() -> resultado`).
        estagio/provedor: chaves da política (teto de retry) e do circuito.
        custo_ok: `() -> bool` — se um novo retry pago ainda cabe no orçamento.
        alternativa: `(politica) -> resultado` — o failover do pilar (ex.: placeholder).
        refresh: `() -> bool` — renova a credencial (classe auth); True se renovou.
        relatorio: dict opcional preenchido com `tentativas`/`failover`/`classes`.

    Returns:
        O resultado de `fn()` (ou do failover).
    """
    circ = _circuitos if _circuitos is not None else circuitos
    # Resolvido em tempo de chamada (não como default) para ser monkeypatchável nos testes.
    _dormir = dormir if dormir is not None else time.sleep
    contexto = contexto or {}
    rel = relatorio if relatorio is not None else {}

    def _failover_ou_dead_letter(classe: str):
        if alternativa is not None and politica.failover:
            rel["failover"] = True
            return alternativa(politica)
        raise ResilienciaEsgotada(classe, {**contexto, "provedor": provedor, "estagio": estagio})

    estado = circ.estado(provedor, politica)
    if estado == ABERTO:
        return _failover_ou_dead_letter(TRANSITORIO)

    cap = politica.cap(estagio)
    if estado == MEIO_ABERTO:
        cap = 1  # só um probe
    elif circ.falhas_recentes(provedor, politica.circuito["janela_saude_seg"]) >= politica.circuito["limiar_falhas"]:
        cap = max(1, cap // 2)  # adaptativo: provedor flaky → mais conservador

    refrescou = False
    tentativa = 0
    while True:
        try:
            resultado = fn()
        except Exception as e:  # noqa: BLE001
            classe = classificar(e)
            rel.setdefault("classes", []).append(classe)
            ctx = {**contexto, "provedor": provedor, "estagio": estagio, "classe": classe, "erro": str(e)}

            if classe == AUTH:
                if refresh is not None and not refrescou and refresh():
                    refrescou = True
                    continue
                raise HaltDestino(ctx, causa=e)
            if classe == QUOTA:
                raise Deferir(QUOTA, politica.defer_horas.get("quota", 24), ctx)
            if classe in (PERMANENTE, RECURSO):
                raise ResilienciaEsgotada(classe, ctx, causa=e)

            # transitório: conta como falha do provedor (alimenta o circuito).
            circ.registrar_falha(provedor)
            rel["tentativas"] = rel.get("tentativas", 0) + 1
            tentativa += 1
            if tentativa >= cap:
                break
            if custo_ok is not None and not custo_ok():
                break  # retry furaria o orçamento — para (resiliência não é isenta do teto)
            espera = proxima_espera(tentativa - 1, politica, retry_after(e), _rng=_rng)
            if espera:
                _dormir(espera)
            continue
        else:
            circ.registrar_sucesso(provedor)
            return resultado

    return _failover_ou_dead_letter(TRANSITORIO)
