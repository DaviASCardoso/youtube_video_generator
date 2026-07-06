"""Thumbnail: imagem de fundo + texto sobreposto por Groq.

Para vídeo longo a thumbnail é a maior alavanca de clique, então a Publicação monta
uma em vez de deixar a plataforma escolher. O design é fixo; a composição é o que se
implementa aqui:

- **Fundo**, cuja *fonte é uma config do painel*: `flux` (IA, via Together) ou `pexels`
  (banco de imagens). No modo flux o **prompt** da imagem é gerado por Groq; no modo
  pexels o **termo de busca** é gerado por Groq.
- **Texto sobreposto**, gerado por Groq a partir do tema/roteiro, composto sobre o
  fundo com fonte/cor/posição/contorno configuráveis (PIL `ImageDraw` + `stroke`).
- Ligável/desligável por tipo (`thumbnail.ativo`) — importa pouco em short-form.

Nenhum provedor novo: fundo e texto reusam FLUX/Pexels/Groq já presentes. Degrada em
vez de quebrar: fundo falho → placeholder; texto falho → tema; fonte ausente → padrão.
Checkpoint em `thumbnail.png` + o texto/diretriz em `publicacao.json`.
"""

import io
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from geracao import checkpoint, pexels
from geracao.compositor import _cobrir, _fundo_placeholder
from geracao.custo import CUSTO_FLUX_IMAGEM, CUSTO_GROQ_CHAMADA, CUSTO_PEXELS
from geracao.generate_image import gerar_imagem
from geracao.generate_script import _chamar_api
from publicacao import registro
from publicacao.configuracao import mesclar_publicacao

# Thumbnail do YouTube: 1280×720 (16:9).
LARGURA = 1280
ALTURA = 720

# Fontes .ttf comuns tentadas quando nenhuma é configurada (fallback final: bitmap do PIL).
_FONTES_FALLBACK = ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf")

_PROMPT_PADRAO_FLUX = (
    "Você cria thumbnails de YouTube de alto clique. A partir do tema e do roteiro, "
    "responda APENAS com um objeto JSON com \"texto\" (chamada curta e impactante, "
    "até ~5 palavras, para sobrepor na imagem) e \"fundo\" (um prompt em inglês para "
    "gerar uma imagem de fundo chamativa)."
)
_PROMPT_PADRAO_PEXELS = (
    "Você cria thumbnails de YouTube de alto clique. A partir do tema e do roteiro, "
    "responda APENAS com um objeto JSON com \"texto\" (chamada curta e impactante, "
    "até ~5 palavras, para sobrepor na imagem) e \"fundo\" (um termo de busca em inglês "
    "para achar uma foto de fundo no banco de imagens)."
)


def _parsear(resposta: str) -> dict:
    resposta = re.sub(r"```(?:json)?\s*", "", resposta).strip().rstrip("`").strip()
    dados = json.loads(resposta)
    return dados if isinstance(dados, dict) else {}


def _system_prompt(assets_dir: Path, fonte_fundo: str) -> str:
    from feedback import guia

    caminho = Path(assets_dir) / "system_prompt_thumbnail.txt"
    base = _PROMPT_PADRAO_PEXELS if fonte_fundo == "pexels" else _PROMPT_PADRAO_FLUX
    if caminho.exists():
        texto = caminho.read_text(encoding="utf-8").strip()
        if texto:
            base = texto
    return guia.compor(assets_dir, "thumbnail", base)


def _texto_e_diretriz(sidecar, config, assets_dir, fonte_fundo, ledger) -> tuple[str, str]:
    tema = str(sidecar.get("tema") or "").strip()
    roteiro = str(sidecar.get("roteiro") or "").strip()
    system = _system_prompt(Path(assets_dir), fonte_fundo)
    user = f"TEMA: {tema}\n\nROTEIRO:\n{roteiro}"
    try:
        bruto = _parsear(_chamar_api(system, user, config))
    except Exception as e:  # noqa: BLE001
        print(f"    [thumbnail] falha ao gerar texto/fundo ({e}) — usando o tema")
        bruto = {}
    if ledger is not None:
        ledger.registrar("thumbnail_texto", "groq", CUSTO_GROQ_CHAMADA, modelo=config.get("groq.modelo"))
    texto = str(bruto.get("texto") or "").strip() or tema
    diretriz = str(bruto.get("fundo") or "").strip() or tema
    return texto, diretriz


def _fundo(config, assets_dir, fonte_fundo, diretriz, indice, ledger) -> Image.Image:
    if fonte_fundo == "pexels":
        dados = pexels.buscar_imagem(diretriz, orientacao="landscape", indice=indice)
        if ledger is not None:
            ledger.registrar(
                "thumbnail_fundo", "pexels" if dados else "placeholder",
                CUSTO_PEXELS if dados else 0.0,
            )
        if dados:
            return Image.open(io.BytesIO(dados))
        return _fundo_placeholder(indice, LARGURA, ALTURA)

    try:
        dados = gerar_imagem(diretriz, config, assets_dir)
        if ledger is not None:
            ledger.registrar("thumbnail_fundo", "flux", CUSTO_FLUX_IMAGEM, modelo=config.get("together.modelo"))
        return Image.open(io.BytesIO(dados))
    except Exception as e:  # noqa: BLE001
        print(f"    [thumbnail] fundo FLUX falhou ({e}) — usando placeholder")
        if ledger is not None:
            ledger.registrar("thumbnail_fundo", "placeholder", 0.0)
        return _fundo_placeholder(indice, LARGURA, ALTURA)


def _carregar_fonte(caminho: str, tamanho: int):
    for tentativa in (caminho, *_FONTES_FALLBACK):
        if not tentativa:
            continue
        try:
            return ImageFont.truetype(tentativa, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _quebrar_linhas(texto, fonte, draw, largura_max) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if draw.textlength(teste, font=fonte) <= largura_max or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _desenhar_texto(img: Image.Image, texto: str, cfg_texto: dict) -> None:
    """Compõe o texto sobre a imagem (best-effort: qualquer falha deixa só o fundo)."""
    if not texto.strip():
        return
    try:
        draw = ImageDraw.Draw(img)
        fonte = _carregar_fonte(cfg_texto.get("fonte", ""), cfg_texto.get("tamanho", 96))
        margem = int(img.width * 0.05)
        linhas = _quebrar_linhas(texto.upper(), fonte, draw, img.width - 2 * margem)

        alturas = [draw.textbbox((0, 0), l, font=fonte)[3] for l in linhas]
        espaco = int((alturas[0] if alturas else 0) * 0.2)
        bloco = sum(alturas) + espaco * (len(linhas) - 1)

        posicao = cfg_texto.get("posicao", "inferior")
        if posicao == "superior":
            y = margem
        elif posicao == "centro":
            y = (img.height - bloco) // 2
        else:
            y = img.height - bloco - margem

        contorno = max(0, int(cfg_texto.get("contorno_largura", 4)))
        for linha, alt in zip(linhas, alturas):
            largura_linha = draw.textlength(linha, font=fonte)
            x = (img.width - largura_linha) // 2
            draw.text(
                (x, y), linha, font=fonte, fill=cfg_texto.get("cor", "#FFFFFF"),
                stroke_width=contorno, stroke_fill=cfg_texto.get("contorno_cor", "#000000"),
            )
            y += alt + espaco
    except Exception as e:  # noqa: BLE001
        print(f"    [thumbnail] falha ao desenhar o texto ({e}) — thumbnail sem texto")


def gerar_thumbnail(sidecar, config, assets_dir, indice=0, ledger=None) -> tuple[Image.Image, dict]:
    """Monta a thumbnail (fundo + texto) e devolve a imagem + o {texto, fundo} usado."""
    cfg_thumb = mesclar_publicacao(config.get_all().get("publicacao"))["thumbnail"]
    fonte_fundo = cfg_thumb.get("fonte_fundo", "flux")

    texto, diretriz = _texto_e_diretriz(sidecar, config, assets_dir, fonte_fundo, ledger)
    fundo = _fundo(config, assets_dir, fonte_fundo, diretriz, indice, ledger)
    img = _cobrir(fundo, LARGURA, ALTURA)
    _desenhar_texto(img, texto, cfg_thumb["texto"])
    return img, {"texto": texto, "fundo": diretriz}


def obter_thumbnail(pasta, config, assets_dir, ledger=None, reaproveitar=True) -> Path | None:
    """Thumbnail com checkpoint. Devolve o caminho do PNG, ou None quando desligada.

    Reaproveita `thumbnail.png` se já existe e valida; senão lê o sidecar do run,
    gera, salva e persiste o texto em `publicacao.json`.
    """
    from geracao import sidecar as sidecar_mod

    cfg_thumb = mesclar_publicacao(config.get_all().get("publicacao"))["thumbnail"]
    if not cfg_thumb.get("ativo"):
        return None

    caminho = Path(pasta) / "thumbnail.png"
    if reaproveitar and checkpoint.artefato_valido(caminho):
        return caminho

    sidecar = sidecar_mod.ler(pasta) or {}
    img, dados_texto = gerar_thumbnail(sidecar, config, assets_dir, ledger=ledger)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    img.save(caminho)
    registro.gravar(pasta, thumbnail=dados_texto)
    return caminho
