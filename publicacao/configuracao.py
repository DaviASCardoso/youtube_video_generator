"""Schema e defaults da configuração de Publicação por tipo.

Fonte da verdade da forma do bloco `publicacao` que cada `tipos/<id>/config.json`
carrega: os defaults (`PUBLICACAO_PADRAO`) e os enums que o Controle importa para
validar os formulários (mesmo padrão de `descoberta.configuracao` e
`geracao.configuracao`).

Este bloco reúne o que é transversal à publicação: o gate de revisão, o timing
(imediato/agendado), visibilidade/audiência/disclosure, os parâmetros dos metadados
(tom/templates/estratégia de tags — o motor é Groq, fixo), a thumbnail, a cota de
upload e o mapa de **destinos** (cada um com seu liga/desliga e defaults de upload).

Migração: o antigo toggle `youtube.publicar` guardava o liga/desliga do canal — seu
papel de enable migra para `destinos.youtube.ativo`, e o papel de humano-no-loop vira
o gate `revisao` (default `auto`). `mesclar_publicacao` semeia `destinos.youtube` e a
privacidade a partir do bloco legado `youtube` para tipos criados antes desta seção,
preservando o comportamento (quem não publicava, segue não publicando).
"""

import copy

# --- Enums (importados pelo Controle para validar os formulários) -----------

# Gate de revisão: auto publica; revisar segura para aprovação humana.
MODOS_REVISAO_PUB = ("auto", "revisar")

# Quando o vídeo vai ao ar: imediato ou agendado (publishAt nativo da plataforma).
MODOS_TIMING = ("imediato", "agendado")

# Audiência declarada (made-for-kids da plataforma).
AUDIENCIAS = ("nao_infantil", "infantil")

# Estratégia de tags que o passo de metadados (Groq) deve seguir.
ESTRATEGIAS_TAGS = ("mistas", "nicho", "amplas")

# Fonte da imagem de fundo da thumbnail (ambas já existem no projeto).
FONTES_FUNDO_THUMB = ("flux", "pexels")

# Posição do texto sobreposto na thumbnail.
POSICOES_TEXTO_THUMB = ("inferior", "superior", "centro")

# O que fazer quando a cota diária de upload é atingida.
ACOES_QUOTA = ("adiar",)

# Destinos que a Publicação conhece. Só o YouTube está implementado; os demais
# são costura (o contrato existe, falta o módulo do destino).
DESTINOS_DISPONIVEIS = ("youtube",)

# --- Defaults ---------------------------------------------------------------

PUBLICACAO_PADRAO = {
    "revisao": "auto",  # auto | revisar
    "timing": {
        "modo": "imediato",  # imediato | agendado
        "horario": "18:00",  # go-live quando agendado (HH:MM)
        "fuso_horario": "America/Sao_Paulo",
    },
    "visibilidade": {
        "privacidade": "public",  # public | unlisted | private
        "audiencia": "nao_infantil",  # nao_infantil | infantil
        "disclosure_sintetico": True,  # flag de mídia sintética (exigida desde jan/2026)
    },
    "metadados": {
        "tom": "",  # tom pedido ao Groq (vazio = neutro/persona do prompt)
        "template_titulo": "",  # molde opcional de título
        "template_descricao": "",  # molde opcional de descrição
        "estrategia_tags": "mistas",  # mistas | nicho | amplas
        "max_tags": 15,
    },
    "thumbnail": {
        "ativo": False,  # off por default (importa pouco em short-form)
        "fonte_fundo": "flux",  # flux | pexels
        "texto": {
            "fonte": "",  # caminho de um .ttf (vazio = fonte padrão do PIL)
            "tamanho": 96,
            "cor": "#FFFFFF",
            "posicao": "inferior",  # inferior | superior | centro
            "contorno_cor": "#000000",
            "contorno_largura": 4,
        },
    },
    "quota": {
        "cap_diario": 5,  # uploads/dia por credencial (5×1600≈8000 de 10000 unidades)
        "acao": "adiar",  # adiar = defere para o dia seguinte
    },
    "destinos": {
        "youtube": {
            "ativo": False,  # migrado de youtube.publicar
            "categoria_id": "22",
            "idioma": "pt-BR",
            "playlist": "",  # id de playlist para adicionar (vazio = nenhuma)
            "tags_base": [],  # tags fixas mescladas com as geradas
            "descricao_base": "",  # rodapé fixo da descrição
        },
    },
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


def _semear_do_youtube_legado(bloco: dict, youtube_legado: dict | None) -> None:
    """Semeia (uma vez) o destino YouTube e a privacidade a partir do bloco legado
    `youtube`, para tipos criados antes deste bloco existir — preservando o
    comportamento: quem tinha `publicar: false`/ausente segue com o destino off.

    Só aplica quando o bloco `bruto` não trouxe `publicacao` (ou não trouxe o
    destino youtube), para não sobrescrever uma configuração já feita no painel.
    """
    if not isinstance(youtube_legado, dict):
        return
    yt = bloco["destinos"]["youtube"]
    yt["ativo"] = bool(youtube_legado.get("publicar", False))
    if youtube_legado.get("categoria_id"):
        yt["categoria_id"] = youtube_legado["categoria_id"]
    if youtube_legado.get("tags"):
        yt["tags_base"] = list(youtube_legado["tags"])
    if youtube_legado.get("descricao_base"):
        yt["descricao_base"] = youtube_legado["descricao_base"]
    if youtube_legado.get("visibilidade"):
        bloco["visibilidade"]["privacidade"] = youtube_legado["visibilidade"]


def mesclar_publicacao(bruto: dict | None, youtube_legado: dict | None = None) -> dict:
    """Completa um bloco `publicacao` (parcial ou ausente) com os defaults.

    Args:
        bruto: O bloco `publicacao` lido do config.json, ou None.
        youtube_legado: O bloco `youtube` legado do mesmo config, usado para semear
            o destino YouTube + privacidade quando `bruto` ainda não tem `publicacao`.

    Returns:
        Um bloco `publicacao` completo.
    """
    tinha_bloco = isinstance(bruto, dict)
    base = _mesclar(PUBLICACAO_PADRAO, bruto) if tinha_bloco else copy.deepcopy(PUBLICACAO_PADRAO)
    # Só migra do legado quando o tipo ainda não tinha o bloco publicacao — depois
    # disso, o que vale é o que o painel salvou.
    if not tinha_bloco:
        _semear_do_youtube_legado(base, youtube_legado)
    return base
