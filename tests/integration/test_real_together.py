"""Chamada real ao Together (geração de imagem). Rode com: pytest --real-api

Atenção: gera uma imagem de verdade (consome cota paga do Together).
"""

import io

import pytest
from PIL import Image

from geracao import generate_image

pytestmark = pytest.mark.real_api


def test_together_gera_imagem(tipo_real, exigir_chave):
    exigir_chave("TOGETHER_API_KEY")
    dados = generate_image.gerar_imagem(
        "a single red apple on a white table, studio light",
        tipo_real.config,
        tipo_real.assets_dir,
    )
    assert isinstance(dados, bytes) and len(dados) > 0
    # os bytes decodificados são uma imagem válida (o Together pode devolver JPEG)
    Image.open(io.BytesIO(dados)).verify()
