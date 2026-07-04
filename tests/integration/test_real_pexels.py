"""Chamada real ao Pexels (foto de fundo). Rode com: pytest --real-api"""

import pytest

from geracao import pexels

pytestmark = pytest.mark.real_api


def test_pexels_baixa_foto(exigir_chave):
    exigir_chave("PEXELS_API_KEY")
    dados = pexels.buscar_imagem("office desk", orientacao="portrait")
    assert dados is not None
    assert len(dados) > 0
