"""Cliente mínimo da API do Pexels para buscar fotos de fundo (banco de imagens).

Só precisa de uma chave gratuita (https://www.pexels.com/api/) na variável de
ambiente PEXELS_API_KEY. Usa apenas a biblioteca padrão (urllib) — sem
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
# bot) antes mesmo de checar a chave. O urllib manda "Python-urllib/x.y" por
# padrão, que é justamente o que ele bloqueia.
USER_AGENT = "Mozilla/5.0 (compatible; GeradorDeVideos/1.0)"


def tem_chave() -> bool:
    return bool(os.getenv("PEXELS_API_KEY"))


def buscar_imagem(termo: str, indice: int = 0, timeout: int = 60) -> bytes | None:
    """Busca uma foto em retrato para o termo e devolve os bytes da imagem.

    `indice` escolhe entre os primeiros resultados (para variar o fundo quando o
    mesmo termo aparece mais de uma vez). Retorna None se não houver chave,
    nenhum resultado, ou se a requisição falhar.
    """
    chave = os.getenv("PEXELS_API_KEY")
    if not chave:
        return None

    params = urllib.parse.urlencode(
        {"query": termo, "orientation": "portrait", "per_page": 8}
    )
    req = urllib.request.Request(
        f"{PEXELS_URL}?{params}",
        headers={"Authorization": chave, "User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read())
    except Exception as e:  # rede, chave inválida, etc — protótipo não deve quebrar
        print(f"    [pexels] falha na busca por '{termo}': {e}")
        return None

    fotos = dados.get("photos", [])
    if not fotos:
        print(f"    [pexels] nenhum resultado para '{termo}'")
        return None

    foto = fotos[indice % len(fotos)]
    # large2x costuma ser ~1024px de largura em retrato — suficiente, o
    # compositor recorta/preenche para 1080x1920 de qualquer forma.
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
        if dados:
            destino = BASE / "saida" / "teste_pexels.jpg"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(dados)
            print(f"Imagem de teste salva em: {destino}")
        else:
            print("Nenhuma imagem retornada.")
