"""Schema e defaults da configuração de Descoberta por tipo.

Este módulo é a **fonte da verdade** da forma do bloco `descoberta` que cada
`tipos/<id>/config.json` carrega: os valores padrão (`DESCOBERTA_PADRAO`) e os
enums que o Controle importa para validar os formulários (mesmo padrão de
`geracao.compositor.POSICOES` / `geracao.generate_image.ASPECT_RATIOS`).

A Descoberta é totalmente config-driven; nada do seu comportamento é hardcoded.
Tudo aqui tem um default sensato, para o sistema rodar sem nenhuma configuração.
"""

import copy

from config.constantes import FEEDS_TRENDS

# --- Enums (importados pelo Controle para validar os formulários) -----------

# Como o dedupe compara um candidato com o que já foi feito: "exato" casa nomes
# normalizados idênticos; "token" usa sobreposição de tokens (pega reescritas).
ESTRATEGIAS_DEDUP = ("exato", "token")

# Gate de revisão por tipo: "auto" manda o tema decidido direto para produção;
# "revisar" deixa o tema num estado pendente até aprovação humana.
MODOS_REVIEW = ("auto", "revisar")

# O que fazer com os candidatos avaliados e não escolhidos de um ciclo.
POLITICAS_RETENCAO = ("descartar", "reter")

# Rótulo trending/evergreen que cada candidato carrega (para o balanço de mix).
CATEGORIAS = ("trending", "evergreen")

# Janelas aceitas pelos feeds .rss do Reddit (/top/.rss?t=...).
REDDIT_PERIODOS = ("hour", "day", "week", "month", "year", "all")

# Nomes das fontes plugáveis (5 externas + 2 input-side/pool).
FONTES_DISPONIVEIS = (
    "trends_mcp",
    "youtube",
    "google_trends",
    "reddit",
    "wikipedia",
    "manual",
    "evergreen",
)

# --- Defaults ---------------------------------------------------------------

DESCOBERTA_PADRAO = {
    # X horas antes do horário de geração em que a descoberta roda (0 = na hora).
    "antecedencia_horas": 2,
    "fontes": {
        "trends_mcp": {"ativo": True, "feed": "Google Trends", "limite": 25},
        # YouTube desligado por padrão: precisa de credencial e gasta cota
        # (search.list ~100 unidades/chamada, compartilhada com o upload).
        "youtube": {
            "ativo": False,
            "limite": 15,
            "consultas": [],
            "canais_nicho": [],
            "regiao": "BR",
        },
        "google_trends": {"ativo": True, "limite": 20, "geo": "BR"},
        "reddit": {"ativo": True, "subreddits": ["brasil"], "limite": 20, "periodo": "day"},
        "wikipedia": {"ativo": True, "limite": 20},
        # Fontes input-side (pool de ideias curadas / evergreen).
        "manual": {"ativo": True},
        "evergreen": {"ativo": True},
    },
    "fit": {"score_minimo": 60},
    "dedup": {"dias": 14, "estrategia": "token", "limiar": 0.8},
    "selecao": {
        "peso_sinal": 0.4,
        "peso_fit": 0.4,
        "peso_frescor": 0.2,
        "meia_vida_horas": 48,
    },
    "evergreen_ratio": 0.3,
    "modo_revisao": "auto",
    "retencao": "descartar",
    "orcamento_avaliacao": 3,
}

# Validação leve de coerência dos defaults (o feed precisa existir na lista real).
assert DESCOBERTA_PADRAO["fontes"]["trends_mcp"]["feed"] in FEEDS_TRENDS


def _mesclar(padrao: dict, bruto: dict) -> dict:
    """Deep-merge de `bruto` sobre `padrao` (só desce em dicts; listas/valores
    do `bruto` substituem por inteiro)."""
    resultado = copy.deepcopy(padrao)
    for chave, valor in bruto.items():
        atual = resultado.get(chave)
        if isinstance(atual, dict) and isinstance(valor, dict):
            resultado[chave] = _mesclar(atual, valor)
        else:
            resultado[chave] = copy.deepcopy(valor)
    return resultado


def mesclar_descoberta(bruto: dict | None) -> dict:
    """Completa um bloco `descoberta` (possivelmente parcial ou ausente) com os
    defaults, para que tipos criados antes desta seção existir funcionem.

    Args:
        bruto: O bloco `descoberta` lido do config.json, ou None.

    Returns:
        Um bloco `descoberta` completo e válido.
    """
    if not isinstance(bruto, dict):
        return copy.deepcopy(DESCOBERTA_PADRAO)
    return _mesclar(DESCOBERTA_PADRAO, bruto)
