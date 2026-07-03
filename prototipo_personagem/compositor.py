"""Protótipo de composição de cena para YouTube Shorts.

Ideia nova para as imagens (substituindo a geração por IA com imagem de
referência, que estava trocando/deformando o personagem):

    fundo (imagem de banco / stock)  +  PNG do personagem por cima, num canto

O personagem é sempre o mesmo (você gera os PNGs manualmente, um por emoção)
e é posicionado num canto respeitando a interface do YouTube Shorts — botões
de curtir/comentar/compartilhar (coluna da direita) e o título/descrição
(faixa de baixo). Assim o rosto do personagem nunca fica escondido atrás da UI.

Este arquivo é só o protótipo de composição visual: ele monta um quadro
(imagem estática) para você ver o enquadramento. A montagem em vídeo (juntar
com áudio, trocar de emoção conforme a narração) vem depois, se você aprovar
o visual.

Rode com:  python -m prototipo_personagem.compositor
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Dimensões e zonas seguras do YouTube Shorts (retrato 9:16, 1080x1920).
# "Zona segura" = área onde o YouTube desenha a própria interface por cima do
# vídeo; nada importante (como o rosto do personagem) deve ficar ali.
# ---------------------------------------------------------------------------
LARGURA = 1080
ALTURA = 1920

# Coluna de botões da direita (curtir, comentar, compartilhar, canal).
ZONA_DIREITA_LARGURA = 160

# Faixa de baixo (@canal, título/descrição, call-to-action, barra de progresso).
ZONA_BAIXO_ALTURA = 360

# Faixa de cima (voltar, buscar, opções).
ZONA_CIMA_ALTURA = 130

# ---------------------------------------------------------------------------
# Posicionamento do personagem.
# Ancorado no canto INFERIOR ESQUERDO: é o único canto livre da UI do Shorts
# (direita = botões, faixa de baixo = legenda). O personagem fica "de pé" no
# canto esquerdo, com a base logo acima da faixa de legenda.
# ---------------------------------------------------------------------------
PERSONAGEM_ALTURA_ALVO = int(ALTURA * 0.62)  # altura do PNG em relação à tela
PERSONAGEM_MARGEM_ESQUERDA = 10
PERSONAGEM_MARGEM_INFERIOR = ZONA_BAIXO_ALTURA + 20  # base logo acima da legenda

PASTA = Path(__file__).parent
PASTA_PERSONAGENS = PASTA / "personagens"
PASTA_FUNDOS = PASTA / "fundos"
PASTA_SAIDA = PASTA / "saida"

# Emoções que o personagem precisa ter (um PNG para cada).
EMOCOES = [
    "neutro",     # padrão / narração comum
    "feliz",      # momentos positivos, boas notícias
    "serio",      # afirmações firmes, alertas
    "pensativo",  # reflexão, "pense sobre isso"
    "surpreso",   # revelações, dados inesperados
    "cetico",     # dúvida/ironia — a cara da persona "Cético Prático"
    "confiante",  # conclusões, chamadas para ação
]

EMOCAO_PADRAO = "neutro"


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    """Tenta uma fonte do sistema; cai na fonte embutida do Pillow se não achar."""
    for nome in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def caminho_personagem(emocao: str) -> Path:
    """Onde o PNG de uma emoção deve estar. Convenção: personagem_<emocao>.png."""
    return PASTA_PERSONAGENS / f"personagem_{emocao}.png"


# ---------------------------------------------------------------------------
# Geradores de PLACEHOLDER — só para você ver o enquadramento antes de ter os
# PNGs de verdade. Assim que você colocar os arquivos reais em personagens/ e
# fundos/, o compositor usa os seus no lugar destes.
# ---------------------------------------------------------------------------
def _fundo_placeholder(indice: int) -> Image.Image:
    """Um fundo em gradiente, simulando uma imagem de banco (stock)."""
    paletas = [
        ((32, 58, 96), (12, 20, 38)),    # azul noite
        ((92, 46, 46), (28, 16, 20)),    # bordô
        ((30, 74, 62), (10, 26, 24)),    # verde profundo
    ]
    topo, base = paletas[indice % len(paletas)]
    img = Image.new("RGB", (LARGURA, ALTURA))
    px = img.load()
    for y in range(ALTURA):
        t = y / ALTURA
        cor = tuple(int(topo[c] + (base[c] - topo[c]) * t) for c in range(3))
        for x in range(LARGURA):
            px[x, y] = cor
    d = ImageDraw.Draw(img)
    d.text((40, ALTURA // 2), "FUNDO (imagem de banco)\ncoloque PNGs/JPGs em fundos/",
           font=_fonte(38), fill=(255, 255, 255))
    return img


def _personagem_placeholder(emocao: str) -> Image.Image:
    """Um bonequinho simples com uma carinha, só para posicionar. Fundo transparente."""
    L, A = 620, 1180
    img = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    corpo = (58, 122, 214, 255)
    # tronco
    d.rounded_rectangle([L * 0.20, A * 0.42, L * 0.80, A], radius=70, fill=corpo)
    # cabeça
    cx, cy, r = L / 2, A * 0.24, A * 0.17
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(240, 214, 190, 255))

    # olhos e boca variando por emoção
    olho_y = cy - r * 0.15
    ox = r * 0.45
    d.ellipse([cx - ox - 14, olho_y - 14, cx - ox + 14, olho_y + 14], fill=(30, 30, 30, 255))
    d.ellipse([cx + ox - 14, olho_y - 14, cx + ox + 14, olho_y + 14], fill=(30, 30, 30, 255))
    boca_y = cy + r * 0.45
    bw = r * 0.5
    if emocao == "feliz":
        d.arc([cx - bw, boca_y - bw, cx + bw, boca_y + bw], 20, 160, fill=(30, 30, 30, 255), width=10)
    elif emocao in ("serio", "confiante"):
        d.line([cx - bw, boca_y, cx + bw, boca_y], fill=(30, 30, 30, 255), width=10)
    elif emocao == "surpreso":
        d.ellipse([cx - 22, boca_y - 22, cx + 22, boca_y + 22], outline=(30, 30, 30, 255), width=10)
    elif emocao == "pensativo":
        d.line([cx - bw * 0.4, boca_y, cx + bw, boca_y - bw * 0.3], fill=(30, 30, 30, 255), width=10)
    elif emocao == "cetico":
        d.line([cx - bw, boca_y + 10, cx + bw, boca_y - 10], fill=(30, 30, 30, 255), width=10)
        # sobrancelha levantada
        d.line([cx + ox - 20, olho_y - 40, cx + ox + 20, olho_y - 55], fill=(30, 30, 30, 255), width=8)
    else:  # neutro
        d.line([cx - bw * 0.7, boca_y, cx + bw * 0.7, boca_y], fill=(30, 30, 30, 255), width=8)

    d.text((L / 2 - 90, A * 0.46), emocao.upper(), font=_fonte(46), fill=(255, 255, 255, 255))
    return img


# ---------------------------------------------------------------------------
# Composição.
# ---------------------------------------------------------------------------
def _cobrir(fundo: Image.Image) -> Image.Image:
    """Redimensiona/recorta o fundo para preencher 1080x1920 (efeito 'cover')."""
    fundo = fundo.convert("RGB")
    escala = max(LARGURA / fundo.width, ALTURA / fundo.height)
    novo = fundo.resize((round(fundo.width * escala), round(fundo.height * escala)))
    x = (novo.width - LARGURA) // 2
    y = (novo.height - ALTURA) // 2
    return novo.crop((x, y, x + LARGURA, y + ALTURA))


def compor(fundo: Image.Image, personagem: Image.Image, mostrar_guias: bool = False) -> Image.Image:
    """Monta a cena: fundo preenchendo a tela + personagem no canto inferior esquerdo."""
    cena = _cobrir(fundo)

    # escala o personagem pela altura alvo, mantendo a proporção
    escala = PERSONAGEM_ALTURA_ALVO / personagem.height
    p = personagem.resize((round(personagem.width * escala), round(personagem.height * escala)))
    x = PERSONAGEM_MARGEM_ESQUERDA
    y = ALTURA - PERSONAGEM_MARGEM_INFERIOR - p.height
    cena.paste(p, (x, y), p)

    if mostrar_guias:
        cena = _desenhar_guias(cena)
    return cena


def _desenhar_guias(cena: Image.Image) -> Image.Image:
    """Marca as zonas da UI do Shorts em vermelho translúcido (só para conferência)."""
    overlay = Image.new("RGBA", cena.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    verm = (220, 40, 40, 70)
    d.rectangle([LARGURA - ZONA_DIREITA_LARGURA, 0, LARGURA, ALTURA], fill=verm)
    d.rectangle([0, ALTURA - ZONA_BAIXO_ALTURA, LARGURA, ALTURA], fill=verm)
    d.rectangle([0, 0, LARGURA, ZONA_CIMA_ALTURA], fill=verm)
    cena = Image.alpha_composite(cena.convert("RGBA"), overlay)
    d2 = ImageDraw.Draw(cena)
    f = _fonte(30)
    d2.text((LARGURA - ZONA_DIREITA_LARGURA + 12, ALTURA // 2), "botões", font=f, fill=(255, 255, 255, 255))
    d2.text((20, ALTURA - ZONA_BAIXO_ALTURA + 20), "título / descrição / CTA", font=f, fill=(255, 255, 255, 255))
    d2.text((20, 40), "voltar / buscar", font=f, fill=(255, 255, 255, 255))
    return cena.convert("RGB")


def _carregar_personagem(emocao: str) -> tuple[Image.Image, bool]:
    """Usa o PNG real da emoção, se existir; senão, um placeholder. Retorna (img, real?)."""
    caminho = caminho_personagem(emocao)
    if caminho.exists():
        return Image.open(caminho).convert("RGBA"), True
    return _personagem_placeholder(emocao), False


def _carregar_fundo(indice: int) -> Image.Image:
    """Usa fundos reais de fundos/, se houver; senão, um gradiente placeholder."""
    reais = sorted(
        p for p in PASTA_FUNDOS.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    )
    if reais:
        return Image.open(reais[indice % len(reais)])
    return _fundo_placeholder(indice)


def compor_cena(fundo_bytes: bytes | None, emocao: str, indice_fundo: int = 0) -> Image.Image:
    """Monta uma cena final (sem guias) a partir dos bytes de um fundo e uma emoção.

    Se `fundo_bytes` for None (ex.: Pexels sem chave ou sem resultado), usa um
    gradiente de placeholder para o protótipo não quebrar.
    """
    if fundo_bytes:
        fundo = Image.open(io.BytesIO(fundo_bytes))
    else:
        fundo = _fundo_placeholder(indice_fundo)

    if emocao not in EMOCOES:
        emocao = EMOCAO_PADRAO
    personagem, _ = _carregar_personagem(emocao)
    return compor(fundo, personagem, mostrar_guias=False)


def gerar_previa() -> None:
    """Renderiza uma prévia por emoção (com guias) + uma versão limpa, em saida/."""
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    usando_reais = any(caminho_personagem(e).exists() for e in EMOCOES)

    for i, emocao in enumerate(EMOCOES):
        personagem, real = _carregar_personagem(emocao)
        fundo = _carregar_fundo(i)

        com_guias = compor(fundo, personagem, mostrar_guias=True)
        com_guias.save(PASTA_SAIDA / f"previa_{emocao}_com_guias.png")

        limpo = compor(fundo, personagem, mostrar_guias=False)
        limpo.save(PASTA_SAIDA / f"previa_{emocao}.png")

        tag = "real" if real else "placeholder"
        print(f"  {emocao:10s} -> previa_{emocao}.png  ({tag})")

    print(f"\nPrévias salvas em: {PASTA_SAIDA}")
    if not usando_reais:
        print("Ainda usando bonecos de placeholder. Coloque seus PNGs em "
              f"{PASTA_PERSONAGENS} para ver o personagem real.")


if __name__ == "__main__":
    print("Gerando prévias de composição (Shorts 1080x1920)...\n")
    gerar_previa()
