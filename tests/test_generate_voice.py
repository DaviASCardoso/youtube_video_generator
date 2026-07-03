import json
from types import SimpleNamespace

import pytest

from config.settings import Config
from scripts import generate_voice
from scripts.generate_voice import _suporta_pitch, gerar_narracao


def _config(tmp_path, voz="v", pitch=0.0):
    caminho = tmp_path / "config.json"
    caminho.write_text(
        json.dumps(
            {"tts": {"idioma": "pt-BR", "voz": voz, "velocidade": 1.0, "pitch": pitch}}
        ),
        encoding="utf-8",
    )
    return Config(caminho)


def test_suporta_pitch():
    assert _suporta_pitch("pt-BR-Neural2-B") is True
    assert _suporta_pitch("pt-BR-Wavenet-E") is True
    # vozes Chirp/Chirp3-HD não aceitam pitch
    assert _suporta_pitch("pt-BR-Chirp3-HD-Enceladus") is False
    assert _suporta_pitch("pt-BR-Chirp-HD-F") is False


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


def _capturar_audioconfig(monkeypatch):
    """Faz AudioConfig capturar seus kwargs; devolve o dict capturado."""
    capturado = {}

    def fake_audioconfig(**kwargs):
        capturado.update(kwargs)
        return object()

    class _ClienteFake:
        def __init__(self, *a, **k):
            pass

        def synthesize_speech(self, **k):
            return SimpleNamespace(audio_content=b"x")

    monkeypatch.setattr(generate_voice.texttospeech, "AudioConfig", fake_audioconfig)
    monkeypatch.setattr(generate_voice.texttospeech, "TextToSpeechClient", _ClienteFake)
    return capturado


def test_pitch_omitido_para_chirp(tmp_path, monkeypatch):
    capturado = _capturar_audioconfig(monkeypatch)
    cfg = _config(tmp_path, voz="pt-BR-Chirp3-HD-Enceladus", pitch=-6.0)
    gerar_narracao("oi", tmp_path / "a.mp3", cfg)
    # pitch não é enviado (a API Chirp o rejeitaria), mesmo com valor no config
    assert "pitch" not in capturado
    assert capturado["speaking_rate"] == 1.0


def test_pitch_presente_para_neural2(tmp_path, monkeypatch):
    capturado = _capturar_audioconfig(monkeypatch)
    cfg = _config(tmp_path, voz="pt-BR-Neural2-B", pitch=-3.0)
    gerar_narracao("oi", tmp_path / "a.mp3", cfg)
    assert capturado["pitch"] == -3.0
