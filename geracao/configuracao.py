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

from geracao.compositor import POSICOES  # cantos (reusa o enum da camada de personagem)

# --- Enums (importados pelo Controle para validar os formulários) -----------

# Provedor de cada estágio. "auto" (visuais) segue a fonte do fundo (visuais.fundo):
# ia → flux (Together), pexels → pexels (foto de banco).
PROVEDORES_ROTEIRO = ("groq",)
PROVEDORES_VISUAIS = ("auto", "flux", "pexels")
PROVEDORES_NARRACAO = ("google",)

# Camadas visuais compostas e independentes (substituem os dois modos empacotados).
# Fonte do fundo: "auto" migra do legado imagens.modo (ia→ia, personagem→pexels).
FONTES_FUNDO = ("auto", "ia", "pexels")
# Camada de personagem, independente do fundo: "auto" migra do legado
# imagens.modo (personagem→sim, ia→não); "sim"/"nao" força.
CAMADAS_PERSONAGEM = ("auto", "sim", "nao")

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
        "provedor": "auto",  # segue a fonte do fundo (visuais.fundo)
        "imagens_por_cena": 1,
        "fallback": "pexels",  # flux falha → foto de banco → placeholder
        # Camadas independentes. "auto" reproduz o comportamento de hoje migrando do
        # legado imagens.modo; qualquer combinação (fundo × personagem) é possível.
        "fundo": "auto",       # fonte do fundo: auto | ia (FLUX) | pexels (foto)
        "personagem": "auto",  # camada de personagem: auto | sim | nao
    },
    "narracao": {
        "provedor": "google",
        "voz_secundaria": "",  # voz de fallback se a primária falhar (vazio = nenhuma)
    },
    "legendas": {
        "ativo": False,
        "fonte": "",            # caminho .ttf (vazio = fonte padrão do sistema)
        "tamanho": 48,
        "cor": "#FFFFFF",
        "posicao": "inferior",
        # Contorno igual ao texto da thumbnail (stroke). 0 = sem contorno (idêntico a hoje).
        "contorno_largura": 0,
        "contorno_cor": "#000000",
    },
    "icones": {
        # Camada de ícones — independente e desligada por padrão (tipos existentes não
        # mudam). Um ícone por cena, quando o conceito da cena pede (null = sem ícone).
        "ativo": False,
        "conjunto": "mdi",  # set do Iconify (mdi = Material Design Icons, Apache-2.0)
        "posicao": "superior_direito",  # canto (reusa o enum da camada de personagem)
        "tamanho_percentual": 12,  # tamanho do ícone como % da altura do canvas
        "margem_lateral": 60,
        "margem_vertical": 60,
        "cor": "#FFFFFF",  # recolore o ícone (hex)
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


# --- Dicas de UI (consumidas pelo motor de formulário do Controle) ----------

UI_HINTS = {
    "roteiro": {"rotulo": "Roteiro"},
    "roteiro.provedor": {"rotulo": "Provedor", "opcoes": PROVEDORES_ROTEIRO},
    "roteiro.duracao_alvo_seg": {"rotulo": "Duração-alvo (segundos, 5–3600)", "min": 5, "max": 3600},
    "roteiro.tom": {"rotulo": "Tom (opcional — vazio mantém a persona do prompt)"},
    "roteiro.min_palavras": {"rotulo": "Mín. de palavras do roteiro (0 = sem mínimo)", "min": 0},
    "roteiro.max_palavras": {"rotulo": "Máx. de palavras do roteiro", "min": 1},
    "visuais": {
        "rotulo": "Visuais (camadas compostas)",
        "ajuda": "Fundo e personagem são independentes: dá para ter fundo por IA com personagem, ou foto de banco sem personagem.",
    },
    "visuais.provedor": {"rotulo": "Provedor (auto segue a fonte do fundo)", "opcoes": PROVEDORES_VISUAIS, "avancado": True},
    "visuais.imagens_por_cena": {"rotulo": "Imagens por cena (1–10)", "min": 1, "max": 10},
    "visuais.fallback": {"rotulo": "Fallback quando o visual falha", "opcoes": FALLBACKS_VISUAIS},
    "visuais.fundo": {
        "rotulo": "Fonte do fundo", "opcoes": FONTES_FUNDO,
        "rotulos_opcoes": {
            "auto": "auto — herda do modo legado (imagens.modo)",
            "ia": "ia — imagem gerada por IA (FLUX/Together)",
            "pexels": "pexels — foto de banco de imagens",
        },
    },
    "visuais.personagem": {
        "rotulo": "Camada de personagem", "opcoes": CAMADAS_PERSONAGEM,
        "ajuda": "Sobrepõe o PNG do personagem (posição/tamanho/margens ficam na aba Config, em Cenas do vídeo).",
        "rotulos_opcoes": {
            "auto": "auto — herda do modo legado (imagens.modo)",
            "sim": "sim — compõe o personagem sobre o fundo",
            "nao": "não — só o fundo, sem personagem",
        },
    },
    "narracao": {"rotulo": "Narração"},
    "narracao.provedor": {"rotulo": "Provedor", "opcoes": PROVEDORES_NARRACAO},
    "narracao.voz_secundaria": {"rotulo": "Voz secundária (fallback — vazio desativa)"},
    "legendas": {"rotulo": "Legendas"},
    "legendas.ativo": {"rotulo": "Queimar legendas no vídeo"},
    "legendas.fonte": {"rotulo": "Fonte (caminho .ttf — vazio = fonte padrão)"},
    "legendas.tamanho": {"rotulo": "Tamanho da fonte (8–200)", "min": 8, "max": 200},
    "legendas.cor": {"rotulo": "Cor (hex, ex: #FFFFFF)"},
    "legendas.posicao": {"rotulo": "Posição", "opcoes": POSICOES_LEGENDA},
    "legendas.contorno_largura": {"rotulo": "Contorno — largura (px, 0 = sem contorno)", "min": 0, "max": 20},
    "legendas.contorno_cor": {"rotulo": "Contorno — cor (hex, ex: #000000)"},
    "icones": {
        "rotulo": "Ícones (camada composta)",
        "ajuda": "Sobrepõe um ícone por cena quando o conceito da cena pede — busca no Iconify (grátis, sem chave) dentro do set escolhido, recolore e compõe no canto. Desligado por padrão.",
    },
    "icones.ativo": {"rotulo": "Sobrepor ícone por cena"},
    "icones.conjunto": {"rotulo": "Set do Iconify (ex.: mdi = Material Design Icons)"},
    "icones.posicao": {"rotulo": "Posição", "opcoes": POSICOES},
    "icones.tamanho_percentual": {"rotulo": "Tamanho (% da altura do canvas, 1–100)", "min": 1, "max": 100},
    "icones.margem_lateral": {"rotulo": "Margem lateral (px)", "min": 0},
    "icones.margem_vertical": {"rotulo": "Margem vertical (px)", "min": 0},
    "icones.cor": {"rotulo": "Cor do ícone (hex, ex: #FFFFFF)"},
    "montagem": {"rotulo": "Montagem"},
    "montagem.musica_fundo": {"rotulo": "Música de fundo"},
    "montagem.musica_fundo.ativo": {"rotulo": "Música de fundo"},
    "montagem.musica_fundo.arquivo": {"rotulo": "Arquivo de música (caminho — vazio = sem música)"},
    "montagem.intro": {"rotulo": "Intro (caminho de vídeo — opcional)"},
    "montagem.outro": {"rotulo": "Outro (caminho de vídeo — opcional)"},
    "variacao": {
        "rotulo": "Variação (0 = idêntico, 1 = sempre varia)",
        "ajuda": "Anti-repetição: varia abertura/estrutura/estilo/música para nenhum vídeo sair igual ao anterior.",
    },
    "variacao.aberturas": {"rotulo": "Aberturas", "min": 0, "max": 1, "passo": "0.05"},
    "variacao.estrutura": {"rotulo": "Estrutura", "min": 0, "max": 1, "passo": "0.05"},
    "variacao.musica": {"rotulo": "Música", "min": 0, "max": 1, "passo": "0.05"},
    "variacao.estilo_visual": {"rotulo": "Estilo visual", "min": 0, "max": 1, "passo": "0.05"},
    "variacao.semente": {"rotulo": "Semente (opcional — fixa a variação para reproduzir)", "tipo": "number"},
    "orcamento": {"rotulo": "Orçamento (USD — teto 0 = sem limite, só mede)"},
    "orcamento.por_video_usd": {"rotulo": "Por vídeo", "min": 0, "passo": "0.01"},
    "orcamento.por_dia_usd": {"rotulo": "Por dia", "min": 0, "passo": "0.01"},
    "orcamento.acao": {"rotulo": "Ao estourar", "opcoes": ACOES_ORCAMENTO},
    "checkpoint": {"rotulo": "Checkpoint"},
    "checkpoint.reaproveitar": {"rotulo": "Reaproveitar artefatos válidos ao reexecutar"},
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


# --- Resolução das camadas visuais ------------------------------------------
#
# As três camadas são independentes, mas "auto" preserva o comportamento dos dois
# modos empacotados de antes, migrando do legado `imagens.modo` sem reescrever nada
# (migração preguiçosa, no mesmo espírito do fallback de `pipeline._modo_imagens`):
#   imagens.modo == "ia"         → fundo "ia",     personagem desligado
#   imagens.modo == "personagem" → fundo "pexels", personagem ligado


def resolver_fundo(cfg_visuais: dict, modo_legado: str | None) -> str:
    """Fonte concreta do fundo ("ia" ou "pexels"). "auto" migra de imagens.modo."""
    fonte = (cfg_visuais or {}).get("fundo", "auto")
    if fonte == "auto":
        return "pexels" if modo_legado == "personagem" else "ia"
    return fonte


def resolver_personagem(cfg_visuais: dict, modo_legado: str | None) -> bool:
    """A camada de personagem está ligada? "auto" migra de imagens.modo."""
    camada = (cfg_visuais or {}).get("personagem", "auto")
    if camada == "auto":
        return modo_legado == "personagem"
    return camada == "sim"
