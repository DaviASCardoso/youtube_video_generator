"""Schema e defaults da configuração de Feedback por tipo.

Fonte da verdade da forma do bloco `feedback` que cada `tipos/<id>/config.json`
carrega: os defaults (`FEEDBACK_PADRAO`) e os enums que o Controle importa para
validar os formulários (mesmo padrão de `descoberta.configuracao`,
`geracao.configuracao` e `publicacao.configuracao`).

Este bloco reúne o que é transversal ao pilar Feedback: quais métricas ingerir e
quais são headline, a agenda de maturação do re-poll, o piso amostral, quais
dimensões atribuir/agregar, a agressividade da aplicação por alvo (advisory/auto),
os limites do ajuste numérico, o tamanho/decaimento do bloco de guia aprendida, o
liga/desliga dos experimentos e o mapa de **destinos** de analytics.

Comportamento default **inerte**: `destinos.youtube.ativo` é `False`, então nenhuma
chamada de analytics é feita e nenhum finding/proposta é gerado até o operador ligar
o destino (e reconsentir o escopo `yt-analytics.readonly`). Toda aplicação é
`advisory` por default — propõe, humano aprova no Controle.
"""

import copy

# --- Enums (importados pelo Controle para validar os formulários) -----------

# Modo de aplicação por alvo: advisory propõe e espera aprovação; auto aplica só.
MODOS_APLICACAO = ("advisory", "auto")

# Métricas que a ingestão sabe coletar (headline = as de maior sinal).
METRICAS_DISPONIVEIS = ("avg_view_pct", "ctr", "views", "watch_time", "subs")

# Dimensões de input às quais a performance pode ser atribuída/agregada.
DIMENSOES = (
    "fonte",
    "categoria",
    "voz",
    "modo_visual",
    "hook",
    "titulo",
    "publish_time",
    "thumbnail",
    "duracao",
)

# Destinos de analytics que o Feedback conhece. Só o YouTube está implementado; os
# demais são costura (o contrato existe, falta o módulo do destino).
DESTINOS_FEEDBACK = ("youtube",)

# --- Defaults ---------------------------------------------------------------

FEEDBACK_PADRAO = {
    "metricas": {
        "ingeridas": ["avg_view_pct", "ctr", "views", "watch_time", "subs"],
        "headline": ["avg_view_pct", "ctr"],
    },
    "repoll_horas": [24, 72, 168, 720],  # maturação: ≈24h/72h/7d/30d, depois para
    "sample_floor": 3,  # piso amostral p/ chamar vencedor/perdedor
    "dimensoes": [
        "fonte",
        "categoria",
        "voz",
        "modo_visual",
        "hook",
        "titulo",
        "publish_time",
        "thumbnail",
        "duracao",
    ],
    "aplicacao": {  # modo por alvo (advisory | auto) — default advisory (gate humano)
        "descoberta": "advisory",
        "geracao": "advisory",
        "publicacao": "advisory",
    },
    "caps_numericos": {
        "max_delta_frac": 0.1,  # ajuste máx. por aplicação em campos 0–1 (frac)
        "max_delta_min": 30,  # ajuste máx. por aplicação no horário (minutos)
    },
    "guia": {
        "top_k": 8,  # nº máx. de diretrizes mantidas por bloco
        "tamanho_max_chars": 800,  # teto do bloco injetado no prompt
        "decaimento_dias": 30,  # meia-vida da confiança sem reconfirmação
    },
    "experimentos": {"ativo": False},  # off por default
    "destinos": {
        "youtube": {"ativo": False},  # off = pilar inerte (nenhuma chamada de analytics)
    },
}


# --- Dicas de UI (consumidas pelo motor de formulário do Controle) ----------

UI_HINTS = {
    "metricas": {"rotulo": "Métricas"},
    "metricas.ingeridas": {
        "rotulo": "Métricas ingeridas (uma por linha)",
        "ajuda": "Disponíveis: " + ", ".join(METRICAS_DISPONIVEIS) + ".",
    },
    "metricas.headline": {
        "rotulo": "Métricas headline (uma por linha)",
        "ajuda": "As de maior sinal — retenção (avg_view_pct) e CTR por default.",
    },
    "repoll_horas": {
        "rotulo": "Agenda de maturação (horas após publicar, uma por linha)",
        "ajuda": "Re-poll nesses marcos; depois do último, para. Ex.: 24, 72, 168, 720.",
    },
    "sample_floor": {
        "rotulo": "Piso amostral (nº mín. de vídeos p/ chamar vencedor)", "min": 1, "max": 100,
    },
    "dimensoes": {
        "rotulo": "Dimensões atribuídas/agregadas (uma por linha)",
        "ajuda": "Disponíveis: " + ", ".join(DIMENSOES) + ".",
    },
    "aplicacao": {
        "rotulo": "Aplicação por alvo",
        "ajuda": "advisory propõe e espera aprovação no Controle; auto aplica sozinho.",
    },
    "aplicacao.descoberta": {"rotulo": "Descoberta", "opcoes": MODOS_APLICACAO},
    "aplicacao.geracao": {"rotulo": "Geração", "opcoes": MODOS_APLICACAO},
    "aplicacao.publicacao": {"rotulo": "Publicação", "opcoes": MODOS_APLICACAO},
    "caps_numericos": {"rotulo": "Limites do ajuste numérico"},
    "caps_numericos.max_delta_frac": {
        "rotulo": "Delta máx. por aplicação em campos 0–1", "min": 0.0, "max": 1.0, "passo": "0.01",
    },
    "caps_numericos.max_delta_min": {
        "rotulo": "Delta máx. no horário (minutos)", "min": 0, "max": 720,
    },
    "guia": {"rotulo": "Bloco de guia aprendida"},
    "guia.top_k": {"rotulo": "Máx. de diretrizes por bloco", "min": 1, "max": 50},
    "guia.tamanho_max_chars": {"rotulo": "Teto do bloco (caracteres)", "min": 0, "max": 5000},
    "guia.decaimento_dias": {"rotulo": "Meia-vida da confiança (dias)", "min": 1, "max": 365},
    "experimentos": {"rotulo": "Experimentos"},
    "experimentos.ativo": {"rotulo": "Rodar experimentos (variantes de título/thumbnail/hook)"},
    "destinos": {"rotulo": "Destinos de analytics"},
    "destinos.youtube": {
        "rotulo": "Destino: YouTube",
        "ajuda": "Reusa a credencial OAuth por tipo. Exige a YouTube Analytics API habilitada e o escopo yt-analytics.readonly (reconsentir uma vez).",
    },
    "destinos.youtube.ativo": {"rotulo": "Ingerir analytics do YouTube"},
}


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


def mesclar_feedback(bruto: dict | None) -> dict:
    """Completa um bloco `feedback` (parcial ou ausente) com os defaults.

    Deep-merge sobre `FEEDBACK_PADRAO`, para que tipos criados antes deste bloco
    existir continuem funcionando (herdam todos os campos novos).

    Args:
        bruto: O bloco `feedback` lido do config.json, ou None.

    Returns:
        Um bloco `feedback` completo.
    """
    if not isinstance(bruto, dict):
        return copy.deepcopy(FEEDBACK_PADRAO)
    return _mesclar(FEEDBACK_PADRAO, bruto)
