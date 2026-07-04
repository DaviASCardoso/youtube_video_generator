"""Cliente mínimo da API do Pexels para buscar fotos de fundo (banco de imagens).

Precisa da variável de ambiente PEXELS_API_KEY (chave gratuita em
https://www.pexels.com/api/). Usa apenas a biblioteca padrão (urllib) — sem
dependências novas.
"""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

PEXELS_URL = "https://api.pexels.com/v1/search"

# Sem um User-Agent "de navegador", o Pexels responde 403 Forbidden (bloqueio de
# bot) antes mesmo de checar a chave — o urllib manda "Python-urllib/x.y" por
# padrão, que é justamente o que ele bloqueia.
USER_AGENT = "Mozilla/5.0 (compatible; GeradorDeVideos/1.0)"


def tem_chave() -> bool:
    return bool(os.getenv("PEXELS_API_KEY"))


def buscar_imagem(
    termo: str,
    orientacao: str = "portrait",
    indice: int = 0,
    timeout: int = 60,
) -> bytes | None:
    """Busca uma foto para o termo e devolve os bytes da imagem.

    Args:
        termo: Termo de busca em inglês.
        orientacao: "portrait", "landscape" ou "square", conforme o formato do vídeo.
        indice: Escolhe entre os primeiros resultados, para variar o fundo
            quando o mesmo termo aparece mais de uma vez no roteiro.
        timeout: Timeout de rede, em segundos.

    Returns:
        Bytes da foto, ou None se não houver chave, nenhum resultado, ou falha
        de rede — quem chama decide o fallback (o compositor usa um placeholder).
    """
    chave = os.getenv("PEXELS_API_KEY")
    if not chave:
        return None

    params = urllib.parse.urlencode(
        {"query": termo, "orientation": orientacao, "per_page": 8}
    )
    req = urllib.request.Request(
        f"{PEXELS_URL}?{params}",
        headers={"Authorization": chave, "User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read())
    except Exception as e:
        print(f"    [pexels] falha na busca por '{termo}': {e}")
        return None

    fotos = dados.get("photos", [])
    if not fotos:
        print(f"    [pexels] nenhum resultado para '{termo}'")
        return None

    foto = fotos[indice % len(fotos)]
    # large2x tem ~1000px+ no lado maior — suficiente, o compositor
    # recorta/preenche para o tamanho do quadro de qualquer forma.
    url_img = foto["src"].get("large2x") or foto["src"].get("original")

    req_img = urllib.request.Request(url_img, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req_img, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        print(f"    [pexels] falha ao baixar imagem de '{termo}': {e}")
        return None


if __name__ == "__main__":
    if not tem_chave():
        print("PEXELS_API_KEY não configurada no .env")
    else:
        dados = buscar_imagem("messy office desk")
        print(f"bytes baixados: {len(dados) if dados else None}")
