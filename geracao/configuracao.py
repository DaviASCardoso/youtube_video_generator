"""Schema e defaults da configuração de Geração por tipo.

Fonte da verdade da forma do bloco `geracao` que cada `tipos/<id>/config.json`
carrega: os defaults (`GERACAO_PADRAO`) e os enums que o Controle importa para
validar os formulários (mesmo padrão de `descoberta.configuracao` e de
`geracao.compositor.POSICOES`).

Os blocos existentes `groq`/`together`/`imagens`/`tts` seguem como **parâmetros do
provedor** (modelo, aspect ratio, voz, etc.) — não são duplicados aqui. Este bloco
adiciona o que é transversal aos estágios: qual provedor cada estágio usa, alvos e
gates do roteiro, legendas, extras de montagem (música/intro/outro), variação,
orçamento e checkpoint. Tudo com default sensato; a saída default equivale à de
hoje (exceto a variação, ligada baixa de propósito).
"""

import copy

# --- Enums (importados pelo Controle para validar os formulários) -----------

# Provedor de cada estágio. "auto" (visuais) deriva de imagens.modo:
# ia → flux (Together), personagem → pexels (foto + PNG do personagem).
PROVEDORES_ROTEIRO = ("groq",)
PROVEDORES_VISUAIS = ("auto", "flux", "pexels")
PROVEDORES_NARRACAO = ("google",)

# Para onde o estágio de visuais degrada quando o provedor principal falha.
FALLBACKS_VISUAIS = ("pexels", "placeholder")

# O que fazer quando um run estouraria o teto de orçamento.
ACOES_ORCAMENTO = ("degradar", "parar")

# Posição das legendas queimadas no vídeo.
POSICOES_LEGENDA = ("inferior", "superior", "centro")

# --- Defaults ---------------------------------------------------------------

GERACAO_PADRAO = {
    "roteiro": {
        "provedor": "groq",
        "duracao_alvo_seg": 60,
        "tom": "",
        # Bounds permissivos = gate de tamanho efetivamente off por padrão
        # (o gate estrutural — roteiro não-vazio — está sempre ligado).
        "min_palavras": 1,
        "max_palavras": 100000,
    },
    "visuais": {
        "provedor": "auto",  # deriva de imagens.modo
        "imagens_por_cena": 1,
        "fallback": "pexels",  # flux falha → foto de banco → placeholder
    },
    "narracao": {
        "provedor": "google",
        "voz_secundaria": "",  # voz de fallback se a primária falhar (vazio = nenhuma)
    },
    "legendas": {
        "ativo": False,
        "tamanho": 48,
        "cor": "#FFFFFF",
        "posicao": "inferior",
    },
    "montagem": {
        "musica_fundo": {"ativo": False, "arquivo": ""},  # arquivo em assets/musica/
        "intro": "",  # nome de arquivo em assets/ (vazio = sem intro)
        "outro": "",
    },
    "variacao": {
        "aberturas": 0.3,
        "estrutura": 0.3,
        "musica": 0.3,
        "estilo_visual": 0.3,
        "semente": None,  # None = aleatória a cada run; int = reproduzível
    },
    "orcamento": {
        "por_video_usd": 1.0,
        "por_dia_usd": 10.0,
        "acao": "degradar",
    },
    "checkpoint": {"reaproveitar": True},
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


def mesclar_geracao(bruto: dict | None) -> dict:
    """Completa um bloco `geracao` (parcial ou ausente) com os defaults, para que
    tipos criados antes desta seção existir funcionem.

    Args:
        bruto: O bloco `geracao` lido do config.json, ou None.

    Returns:
        Um bloco `geracao` completo.
    """
    if not isinstance(bruto, dict):
        return copy.deepcopy(GERACAO_PADRAO)
    return _mesclar(GERACAO_PADRAO, bruto)
