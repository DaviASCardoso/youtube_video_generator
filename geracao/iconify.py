"""Cliente do Iconify — busca e rasteriza um ícone para o conceito de uma cena.

O Iconify é público, **sem chave e sem conta**: 300k+ ícones de código aberto em 200+
sets. Este cliente:

- **busca** o ícone dentro do set configurado —
  ``GET https://api.iconify.design/search?query={conceito}&prefix={set}&limit=1``
  devolve ``{"icons": ["mdi:cash", ...]}`` (nome no formato ``prefixo:nome``);
- **baixa** o SVG — ``GET https://api.iconify.design/{prefixo}/{nome}.svg?color={cor}``
  (o param ``color`` recolore o traço);
- **rasteriza** o SVG para PNG transparente com cairosvg (moviepy/PIL precisam de
  raster, não de vetor).

Só usa a biblioteca padrão para a rede (urllib), no mesmo estilo de
``descoberta/trends.py`` — sem dependência nova de rede. Cacheia por **conceito+set**
em disco, então o mesmo conceito não é rebaixado entre cenas nem entre runs. Qualquer
falha — sem match, erro de rede, erro de rasterização — devolve ``None`` e a cena sai
**sem ícone** (degrada em vez de quebrar).
"""

import json
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

CONJUNTO_PADRAO = "mdi"  # Material Design Icons (Apache-2.0, sem atribuição)

BASE = "https://api.iconify.design"

# Sem um User-Agent "de navegador", APIs atrás de proteção anti-bot podem responder
# 403 — barato prevenir (mesma precaução de trends.py/pexels.py).
USER_AGENT = "Mozilla/5.0 (compatible; GeradorDeVideos/1.0)"

# Tamanho da rasterização (px). O SVG do Iconify vem com width/height "1em"; damos um
# tamanho fixo generoso e o compositor redimensiona conforme o canvas.
TAMANHO_RASTER = 512


def _cache_padrao() -> Path:
    """Cache global (persistente entre runs). Resolvido preguiçosamente para não
    importar config no topo — a raiz de saída pode ser reconfigurada no painel."""
    from config import caminhos

    return caminhos.raiz("saida") / "_cache_icones"


def _slug(texto: str) -> str:
    """Nome de arquivo seguro para a chave de cache."""
    texto = re.sub(r"[^a-z0-9]+", "_", texto.strip().lower())
    return texto.strip("_") or "icone"


def _baixar(url: str, timeout: int) -> bytes | None:
    """GET simples; devolve os bytes ou None em qualquer falha (rede, HTTP, etc.)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:  # noqa: BLE001 (degradação deliberada: sem ícone)
        print(f"    [iconify] falha ao baixar {url}: {e}")
        return None


def _buscar_nome(conceito: str, prefixo: str, timeout: int) -> str | None:
    """Nome do 1º ícone que casa com o conceito dentro do set (``prefixo:nome``)."""
    query = urllib.parse.urlencode({"query": conceito, "prefix": prefixo, "limit": 1})
    dados = _baixar(f"{BASE}/search?{query}", timeout)
    if not dados:
        return None
    try:
        obj = json.loads(dados)
    except json.JSONDecodeError:
        return None
    icones = obj.get("icons") or []
    return icones[0] if icones and isinstance(icones[0], str) else None


def _baixar_svg(nome: str, cor: str | None, timeout: int) -> bytes | None:
    """Baixa o SVG do ícone ``prefixo:nome`` (recolorido se `cor` vier)."""
    if ":" not in nome:
        return None
    prefixo, nome_icone = nome.split(":", 1)
    url = f"{BASE}/{prefixo}/{nome_icone}.svg"
    if cor:
        url += "?" + urllib.parse.urlencode({"color": cor})
    return _baixar(url, timeout)


def _rasterizar_svg(svg_bytes: bytes, tamanho_px: int) -> bytes:
    """Rasteriza o SVG num PNG transparente. cairosvg é importado aqui (não no topo)
    para o módulo carregar mesmo sem a dependência instalada, e para os testes poderem
    substituir esta função sem tocar em rede/cairo."""
    import cairosvg

    return cairosvg.svg2png(
        bytestring=svg_bytes, output_width=tamanho_px, output_height=tamanho_px
    )


def buscar_icone(
    conceito: str,
    prefixo: str = CONJUNTO_PADRAO,
    cor: str | None = None,
    destino: str | Path | None = None,
    cache_dir: str | Path | None = None,
    tamanho_px: int = TAMANHO_RASTER,
    timeout: int = 30,
) -> Path | None:
    """Devolve o PNG do ícone que casa com `conceito` dentro do set `prefixo`.

    Fluxo: cache (conceito+set) → busca no Iconify → baixa o SVG → rasteriza → cacheia.
    Se `destino` for informado, copia o PNG cacheado para lá (a pasta do run) e devolve
    esse caminho; senão devolve o caminho no cache.

    Qualquer falha (conceito vazio, sem match, rede, rasterização) devolve **None** —
    quem chama simplesmente renderiza a cena sem ícone.
    """
    conceito = (conceito or "").strip().lower()
    if not conceito:
        return None

    cache_dir = Path(cache_dir) if cache_dir else _cache_padrao()
    chave = _slug(f"{prefixo}_{conceito}_{cor or 'default'}")
    cache_png = cache_dir / f"{chave}.png"

    if not cache_png.exists():
        nome = _buscar_nome(conceito, prefixo, timeout)
        if not nome:
            print(f"    [iconify] sem ícone para '{conceito}' no set '{prefixo}'.")
            return None
        svg = _baixar_svg(nome, cor, timeout)
        if not svg:
            return None
        try:
            png = _rasterizar_svg(svg, tamanho_px)
        except Exception as e:  # noqa: BLE001 (degradação deliberada: sem ícone)
            print(f"    [iconify] falha ao rasterizar '{nome}': {e}")
            return None
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_png.write_bytes(png)

    if destino is None:
        return cache_png

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cache_png, destino)
    return destino


if __name__ == "__main__":
    import sys

    conceito = sys.argv[1] if len(sys.argv) > 1 else "money"
    prefixo = sys.argv[2] if len(sys.argv) > 2 else CONJUNTO_PADRAO
    caminho = buscar_icone(conceito, prefixo=prefixo, cor="#FFFFFF")
    print(f"{conceito!r} @ {prefixo} -> {caminho}")
