import json
from types import SimpleNamespace

import pytest

from config.settings import Config
from scripts import generate_voice
from scripts.generate_voice import gerar_narracao


def _config(tmp_path):
    caminho = tmp_path / "config.json"
    caminho.write_text(
        json.dumps(
            {"tts": {"idioma": "pt-BR", "voz": "v", "velocidade": 1.0, "pitch": 0.0}}
        ),
        encoding="utf-8",
    )
    return Config(caminho)


def test_texto_vazio_levanta(tmp_path):
    # levanta antes de instanciar qualquer cliente — não precisa de mock
    with pytest.raises(ValueError):
        gerar_narracao("   ", tmp_path / "saida.mp3", _config(tmp_path))


def test_gera_arquivo_de_audio(tmp_path, monkeypatch):
    class _ClienteFake:
        def __init__(self, *a, **k):
            pass

        def synthesize_speech(self, **kwargs):
            return SimpleNamespace(audio_content=b"conteudo-mp3")

    monkeypatch.setattr(
        generate_voice.texttospeech, "TextToSpeechClient", _ClienteFake
    )

    saida = tmp_path / "sub" / "narracao.mp3"
    resultado = gerar_narracao("olá mundo", saida, _config(tmp_path))
    assert resultado == saida
    assert saida.read_bytes() == b"conteudo-mp3"  # cria a pasta pai e escreve
