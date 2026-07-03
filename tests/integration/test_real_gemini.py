"""Chamada real ao Gemini (tendência -> tema). Rode com: pytest --real-api"""

import pytest

from scripts import gemini
from scripts.gemini import TemaTendencia

pytestmark = pytest.mark.real_api


def test_gemini_gera_tema(exigir_chave):
    exigir_chave("GEMINI_API_KEY")
    resultado = gemini.gerar_tema_de_tendencia(
        "project hail mary",
        "Você transforma um tema em alta num tema de vídeo curto para um canal "
        "de desenvolvimento pessoal cético. Responda em português do Brasil.",
    )
    assert isinstance(resultado, TemaTendencia)
    assert resultado.tema.strip() != ""
    assert resultado.justificativa.strip() != ""
