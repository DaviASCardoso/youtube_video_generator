"""Chamada real ao Gemini (avaliação de fit). Rode com: pytest --real-api"""

import pytest

from descoberta import gemini
from descoberta.gemini import AvaliacaoFit

pytestmark = pytest.mark.real_api


def test_gemini_avalia_fit(exigir_chave):
    exigir_chave("GEMINI_API_KEY")
    resultado = gemini.avaliar_fit(
        "project hail mary",
        "Você avalia se um tema em alta rende um bom vídeo curto para um canal "
        "de desenvolvimento pessoal cético. Responda em português do Brasil.",
    )
    assert isinstance(resultado, AvaliacaoFit)
    assert isinstance(resultado.aceito, bool)
    assert 0 <= resultado.score <= 100
    assert resultado.tema.strip() != ""
