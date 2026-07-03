"""Chamada real ao Google Cloud TTS (narração). Rode com: pytest --real-api"""

import pytest

from scripts import generate_voice

pytestmark = pytest.mark.real_api


def test_tts_gera_mp3(tipo_real, exigir_chave, tmp_path):
    exigir_chave("GOOGLE_APPLICATION_CREDENTIALS")
    saida = generate_voice.gerar_narracao(
        "Teste rápido de narração.",
        tmp_path / "narracao.mp3",
        tipo_real.config,
    )
    assert saida.exists()
    conteudo = saida.read_bytes()
    assert len(conteudo) > 0
    # MP3 começa com um frame sync (0xFF 0xEx) ou uma tag ID3
    assert conteudo[:3] == b"ID3" or conteudo[0] == 0xFF
