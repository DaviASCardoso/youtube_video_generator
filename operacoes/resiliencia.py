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
