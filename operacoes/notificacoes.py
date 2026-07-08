"""Notificações push via ntfy (https://ntfy.sh) — o canal pelo qual o sistema
alcança você quando não está olhando o painel.

Emissão é um POST HTTP simples (só urllib da stdlib, mesmo padrão de
`geracao/pexels.py`/`descoberta/trends.py` — sem dependência nova). Os campos
**sensíveis** ficam no `.env` (fora da camada HTTP, como as demais credenciais):

- `NTFY_SERVER`  (opcional, default `https://ntfy.sh`; troque por um self-hosted)
- `NTFY_TOPIC`   (o tópico; num servidor público ele **é a senha**, escolha algo
                  impossível de adivinhar) — **sem ele, tudo é no-op**
- `NTFY_TOKEN`   (opcional, token de acesso Bearer)

O que é **tunável e não-secreto** (liga/desliga por categoria, prioridade, horas de
silêncio) vive no `config/sistema.json`, bloco `notificacoes`, editável na aba
Notificações do painel — o Controle é dono dessa configuração.

Política default (decidida na spec — silenciosa, nunca spam): o master vem **desligado**
e cada categoria tem um default. As categorias que pedem atenção (`run_falhou`,
`credencial`, `cota_atingida`, `disco_baixo`, `scheduler_parado`, `revisao_pendente`)
vêm ligadas em prioridade `high`; as de rotina (`video_publicado`, `run_concluido`,
`etapa`) vêm desligadas (o tier grátis é 250 msgs/dia). Nada muda para o sistema rodar:
sem `ativo` e sem `NTFY_TOPIC`, `emitir` é um no-op.
"""

import copy
import os
import urllib.request
from datetime import datetime

from dotenv import load_dotenv

from config.sistema import sistema

load_dotenv()

SERVIDOR_PADRAO = "https://ntfy.sh"

# --- Enums (importados pelo Controle para validar a aba Notificações) -------

# Prioridades que o ntfy aceita (X-Priority: 1..5 / min..urgent).
PRIORIDADES = ("min", "low", "default", "high", "urgent")

# Categorias de evento. As "críticas" pedem atenção e furam as horas de silêncio;
# as de rotina são silenciosas por padrão e são suprimidas no silêncio.
CATEGORIAS_CRITICAS = (
    "run_falhou",
    "job_dead_letter",
    "credencial",
    "cota_atingida",
    "disco_baixo",
    "scheduler_parado",
    "revisao_pendente",
)
CATEGORIAS_ROTINA = ("video_publicado", "run_concluido", "etapa")
CATEGORIAS = CATEGORIAS_CRITICAS + CATEGORIAS_ROTINA

# --- Defaults (bloco `notificacoes` do sistema.json) ------------------------

NOTIFICACOES_PADRAO = {
    "ativo": False,  # master: nada é enviado até você ligar
    "horas_silencio": {"ativo": False, "inicio": "22:00", "fim": "08:00"},
    "categorias": {
        # críticas: ligadas em high (a spec pede notificar só o que precisa de atenção)
        "run_falhou": {"ativo": True, "prioridade": "high"},
        "job_dead_letter": {"ativo": True, "prioridade": "high"},
        "credencial": {"ativo": True, "prioridade": "high"},
        "cota_atingida": {"ativo": True, "prioridade": "high"},
        "disco_baixo": {"ativo": True, "prioridade": "high"},
        "scheduler_parado": {"ativo": True, "prioridade": "high"},
        "revisao_pendente": {"ativo": True, "prioridade": "high"},
        # rotina: desligadas (inundariam o telefone — 1+ por vídeo por dia)
        "video_publicado": {"ativo": False, "prioridade": "default"},
        "run_concluido": {"ativo": False, "prioridade": "default"},
        "etapa": {"ativo": False, "prioridade": "low"},
    },
}


# --- Dicas de UI (consumidas pelo motor de formulário do Controle) ----------

_ROTULOS_CATEGORIA = {
    "run_falhou": "Run falhou (após retries)",
    "job_dead_letter": "Run em dead-letter (resiliência esgotada)",
    "credencial": "Credencial expirando/expirada",
    "cota_atingida": "Cota de upload atingida",
    "disco_baixo": "Disco/NAS baixo",
    "scheduler_parado": "Scheduler parado",
    "revisao_pendente": "Item aguardando revisão",
    "video_publicado": "Vídeo publicado (rotina)",
    "run_concluido": "Run concluído (rotina)",
    "etapa": "Progresso por etapa (rotina)",
}

UI_HINTS = {
    "ativo": {"rotulo": "Ativar notificações (interruptor geral)"},
    "horas_silencio": {"rotulo": "Horas de silêncio (suprime as não-críticas)"},
    "horas_silencio.ativo": {"rotulo": "Ativar horas de silêncio"},
    "horas_silencio.inicio": {"rotulo": "Início", "tipo": "time"},
    "horas_silencio.fim": {"rotulo": "Fim", "tipo": "time"},
    "categorias": {"rotulo": "Eventos"},
}
for _cat, _rot in _ROTULOS_CATEGORIA.items():
    UI_HINTS[f"categorias.{_cat}"] = {"rotulo": _rot}
    UI_HINTS[f"categorias.{_cat}.ativo"] = {"rotulo": "Notificar"}
    UI_HINTS[f"categorias.{_cat}.prioridade"] = {"rotulo": "Prioridade", "opcoes": PRIORIDADES}


def _mesclar(padrao: dict, bruto: dict) -> dict:
    """Deep-merge de `bruto` sobre `padrao` (só desce em dicts)."""
    resultado = copy.deepcopy(padrao)
    for chave, valor in bruto.items():
        atual = resultado.get(chave)
        if isinstance(atual, dict) and isinstance(valor, dict):
            resultado[chave] = _mesclar(atual, valor)
        else:
            resultado[chave] = copy.deepcopy(valor)
    return resultado


def mesclar_notificacoes(bruto: dict | None) -> dict:
    """Completa um bloco `notificacoes` (parcial/ausente) com os defaults."""
    if not isinstance(bruto, dict):
        return copy.deepcopy(NOTIFICACOES_PADRAO)
    return _mesclar(NOTIFICACOES_PADRAO, bruto)


def config() -> dict:
    """Lê o bloco `notificacoes` do sistema (mesclado com os defaults)."""
    try:
        bruto = sistema.get("notificacoes")
    except KeyError:
        bruto = None
    return mesclar_notificacoes(bruto)


# --- Estado do canal (usado pelo painel para mostrar status) ----------------


def topico() -> str | None:
    return os.getenv("NTFY_TOPIC") or None


def servidor() -> str:
    return os.getenv("NTFY_SERVER") or SERVIDOR_PADRAO


def configurado() -> bool:
    """True quando há tópico ntfy — o mínimo para uma mensagem chegar ao telefone."""
    return bool(topico())


# --- Política de silêncio ---------------------------------------------------


def _dentro_do_silencio(agora: str, inicio: str, fim: str) -> bool:
    """Se `agora` (HH:MM) cai na janela [inicio, fim), tratando a virada da meia-noite
    (ex.: 22:00–08:00)."""
    if inicio == fim:
        return False
    if inicio < fim:
        return inicio <= agora < fim
    # janela que cruza a meia-noite
    return agora >= inicio or agora < fim


def _silenciado(categoria: str, cfg: dict, agora: datetime) -> bool:
    hs = cfg.get("horas_silencio", {})
    if not hs.get("ativo"):
        return False
    if categoria in CATEGORIAS_CRITICAS:
        return False  # críticas furam o silêncio
    return _dentro_do_silencio(agora.strftime("%H:%M"), hs.get("inicio", ""), hs.get("fim", ""))


# --- Emissão ----------------------------------------------------------------


def _postar(titulo: str, mensagem: str, prioridade: str, timeout: int = 10) -> bool:
    """POST cru no ntfy. Devolve True se enviou; degrada (nunca levanta) em falha."""
    top = topico()
    if not top:
        return False

    # http.client codifica headers em latin-1; títulos em português (acentos) cabem,
    # emoji não — por isso os títulos aqui são texto acentuado simples, sem emoji.
    headers = {"Title": titulo, "Priority": prioridade}
    token = os.getenv("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        f"{servidor().rstrip('/')}/{top}",
        data=mensagem.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception as e:
        print(f"    [ntfy] falha ao enviar '{titulo}': {e}")
        return False


def emitir(categoria: str, titulo: str, mensagem: str, prioridade: str | None = None) -> bool:
    """Envia uma notificação da `categoria`, respeitando a config do painel.

    No-op silencioso (devolve False) quando: o master está desligado, não há tópico
    ntfy, a categoria está desligada, ou estamos em horas de silêncio (categorias não
    críticas). Nunca levanta — uma falha de rede não pode derrubar quem chama.
    """
    cfg = config()
    if not cfg.get("ativo"):
        return False
    if not configurado():
        return False

    cat = cfg.get("categorias", {}).get(categoria)
    if not cat or not cat.get("ativo"):
        return False

    if _silenciado(categoria, cfg, datetime.now()):
        return False

    return _postar(titulo, mensagem, prioridade or cat.get("prioridade", "default"))


def enviar_teste() -> bool:
    """Manda uma notificação de teste para confirmar que o telefone recebe.

    Ignora o master/categorias/silêncio de propósito (é para testar antes de ligar),
    mas ainda precisa de um tópico ntfy configurado.
    """
    return _postar(
        "Teste de notificação",
        "Se você recebeu isto, o ntfy está configurado corretamente.",
        "default",
    )
