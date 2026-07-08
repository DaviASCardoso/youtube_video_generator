"""Composição de cena: foto de fundo + PNG do personagem num canto.

Usado pelo modo de imagens "personagem" (veja imagens.modo no config.json do
tipo): em vez de gerar a cena inteira por IA, o fundo é uma foto de banco de
imagens (Pexels) e o personagem — sempre o mesmo, com um PNG por emoção — é
sobreposto num canto configurável, deixando livre a área da interface do
YouTube (botões, título/descrição).

Os PNGs do personagem vivem em tipos/<id>/assets/personagens/, um por emoção:
personagem_<emocao>.png. O "neutro" é obrigatório (é o fallback quando a
emoção pedida não existe); as demais são opcionais.
"""

import io
from pathlib import Path

from PIL import Image

from config.settings import Config

# Conjuntos autoritativos — o schema Pydantic do painel importa daqui, em vez
# de duplicar as listas (mesmo padrão de ASPECT_RATIOS em generate_image.py).
EMOCOES = ("neutro", "feliz", "serio", "pensativo", "surpreso", "cetico", "confiante")
EMOCAO_PADRAO = "neutro"

POSICOES = (
    "inferior_esquerdo",
    "inferior_direito",
    "superior_esquerdo",
    "superior_direito",
)


def caminho_personagem(assets_dir: Path, emocao: str) -> Path:
    return Path(assets_dir) / "personagens" / f"personagem_{emocao}.png"


def validar_personagens(assets_dir: Path) -> None:
    """Confere o pré-requisito do modo "personagem" antes de gastar API.

    Raises:
        FileNotFoundError: Se o PNG neutro (fallback obrigatório) não existir.
    """
    neutro = caminho_personagem(assets_dir, EMOCAO_PADRAO)
    if not neutro.exists():
        raise FileNotFoundError(
            f"Modo 'personagem' exige ao menos o PNG neutro do personagem em "
            f"{neutro} (é o fallback para emoções sem PNG próprio)."
        )


def _carregar_personagem(assets_dir: Path, emocao: str) -> Image.Image:
    if emocao not in EMOCOES:
        emocao = EMOCAO_PADRAO

    caminho = caminho_personagem(assets_dir, emocao)
    if not caminho.exists():
        caminho = caminho_personagem(assets_dir, EMOCAO_PADRAO)

    return Image.open(caminho).convert("RGBA")


def _fundo_placeholder(indice: int, largura: int, altura: int) -> Image.Image:
    """Gradiente simples para quando o Pexels falhar/não tiver chave — o vídeo
    sai mesmo assim, em vez de derrubar a execução inteira."""
    paletas = [
        ((32, 58, 96), (12, 20, 38)),
        ((92, 46, 46), (28, 16, 20)),
        ((30, 74, 62), (10, 26, 24)),
    ]
    topo, base = paletas[indice % len(paletas)]
    img = Image.new("RGB", (largura, altura))
    px = img.load()
    for y in range(altura):
        t = y / altura
        cor = tuple(int(topo[c] + (base[c] - topo[c]) * t) for c in range(3))
        for x in range(largura):
            px[x, y] = cor
    return img


def _cobrir(fundo: Image.Image, largura: int, altura: int) -> Image.Image:
    """Redimensiona/recorta o fundo para preencher o quadro (efeito 'cover')."""
    fundo = fundo.convert("RGB")
    escala = max(largura / fundo.width, altura / fundo.height)
    novo = fundo.resize((round(fundo.width * escala), round(fundo.height * escala)))
    x = (novo.width - largura) // 2
    y = (novo.height - altura) // 2
    return novo.crop((x, y, x + largura, y + altura))


def compor_fundo(
    fundo_bytes: bytes | None, config: Config, indice: int = 0
) -> Image.Image:
    """A **camada de fundo**: a foto do banco (ou um placeholder) recortada para o
    canvas. É o que a camada de personagem sobrepõe — e o que sai sozinho quando a
    camada de personagem está desligada.

    Args:
        fundo_bytes: Bytes da foto de fundo (None -> gradiente de placeholder).
        config: Config do tipo (lê imagens.largura/altura).
        indice: Índice da cena, só para variar a cor do placeholder.
    """
    largura = config.get("imagens.largura")
    altura = config.get("imagens.altura")
    fundo = Image.open(io.BytesIO(fundo_bytes)) if fundo_bytes else _fundo_placeholder(
        indice, largura, altura
    )
    return _cobrir(fundo, largura, altura)


def sobrepor_personagem(
    cena: Image.Image, emocao: str, config: Config, assets_dir: Path
) -> Image.Image:
    """A **camada de personagem**: cola o PNG da emoção sobre um quadro já pronto.

    Independente da fonte do fundo — funciona sobre uma foto do Pexels **ou** sobre
    uma imagem gerada por IA. Posição/tamanho/margens vêm de `imagens.personagem.*`;
    o canvas de referência é o do próprio quadro recebido (não o config), para
    posicionar certo mesmo quando o fundo por IA tem outra proporção.

    Args:
        cena: Quadro de fundo já recortado (modificado in-place e devolvido).
        emocao: Emoção do personagem (fora de EMOCOES -> neutro).
        config: Config do tipo (lê imagens.personagem.*).
        assets_dir: Pasta de assets do tipo (onde estão os PNGs do personagem).
    """
    largura, altura = cena.width, cena.height
    posicao = config.get("imagens.personagem.posicao")
    altura_pct = config.get("imagens.personagem.altura_percentual")
    margem_lateral = config.get("imagens.personagem.margem_lateral")
    margem_vertical = config.get("imagens.personagem.margem_vertical")

    personagem = _carregar_personagem(assets_dir, emocao)
    escala = (altura * altura_pct / 100) / personagem.height
    p = personagem.resize(
        (round(personagem.width * escala), round(personagem.height * escala))
    )

    x = margem_lateral if "esquerdo" in posicao else largura - margem_lateral - p.width
    y = margem_vertical if "superior" in posicao else altura - margem_vertical - p.height
    cena.paste(p, (x, y), p)
    return cena


def compor_cena(
    fundo_bytes: bytes | None,
    emocao: str,
    config: Config,
    assets_dir: Path,
    indice: int = 0,
) -> Image.Image:
    """Fundo + personagem num só passo (as duas camadas empilhadas).

    Mantido por compatibilidade; o pipeline agora empilha as camadas separadamente
    (`compor_fundo` + `sobrepor_personagem`) para que cada uma seja independente.
    """
    cena = compor_fundo(fundo_bytes, config, indice)
    return sobrepor_personagem(cena, emocao, config, assets_dir)
