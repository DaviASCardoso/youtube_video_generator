"""Chamada real ao Groq (roteiro). Rode com: pytest --real-api"""

import pytest

from geracao import generate_script

pytestmark = pytest.mark.real_api


def test_groq_responde(tipo_real, exigir_chave):
    exigir_chave("GROQ_API_KEY")
    resposta = generate_script._chamar_api(
        "Você responde em uma única palavra.",
        "Responda apenas: OK",
        tipo_real.config,
    )
    assert isinstance(resposta, str)
    assert resposta.strip() != ""
