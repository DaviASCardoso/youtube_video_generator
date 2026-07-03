import json
from types import SimpleNamespace

import pytest

from config.settings import Config
from scripts import pipeline
from scripts.pipeline import _modo_imagens, gerar_video


def _tipo_com_modo(tmp_path, dados_imagens):
    caminho = tmp_path / "config.json"
    dados = {} if dados_imagens is None else {"imagens": dados_imagens}
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return SimpleNamespace(config=Config(caminho))


def test_modo_imagens_le_config(tmp_path):
    tipo = _tipo_com_modo(tmp_path, {"modo": "personagem"})
    assert _modo_imagens(tipo) == "personagem"


def test_modo_imagens_fallback_ia(tmp_path):
    # tipo antigo sem a seção imagens -> "ia"
    tipo = _tipo_com_modo(tmp_path, None)
    assert _modo_imagens(tipo) == "ia"


# --- gerar_video: seleção de ramo + fiação, sem render real ---

class _FakeAudio:
    duration = 1.5

    def __init__(self, *a, **k):
        pass


class _FakeImageClip:
    def __init__(self, *a, **k):
        pass

    def with_duration(self, d):
        return self

    def with_audio(self, a):
        return self


class _FakeVideo:
    def __init__(self):
        self.escrito = None

    def write_videofile(self, caminho, **k):
        self.escrito = caminho


@pytest.fixture
def moviepy_falso(monkeypatch):
    video = _FakeVideo()
    monkeypatch.setattr(pipeline, "AudioFileClip", _FakeAudio)
    monkeypatch.setattr(pipeline, "ImageClip", _FakeImageClip)
    monkeypatch.setattr(pipeline, "concatenate_videoclips", lambda clipes, **k: video)
    monkeypatch.setattr(pipeline, "gerar_narracao", lambda *a, **k: None)
    return video


def test_gerar_video_ramo_personagem(tmp_path, sistema_temp, make_tipo, moviepy_falso, monkeypatch):
    tipo = make_tipo()  # config tem imagens.modo = "personagem"
    chamado = {}

    def fake_personagem(tema, tipo, base, pasta_imagens):
        chamado["personagem"] = True
        return [(1, "frase um")]

    monkeypatch.setattr(pipeline, "_gerar_cenas_personagem", fake_personagem)
    monkeypatch.setattr(
        pipeline, "_gerar_cenas_ia", lambda *a: pytest.fail("não deveria chamar ia")
    )

    caminho = gerar_video("tema", tipo, tmp_path / "out")
    assert chamado.get("personagem") is True
    assert caminho == tmp_path / "out" / "video_final.mp4"
    assert moviepy_falso.escrito == str(caminho)


def test_gerar_video_ramo_ia(tmp_path, sistema_temp, make_tipo, moviepy_falso, monkeypatch):
    tipo = make_tipo(config_extra={"imagens": {"modo": "ia"}})
    chamado = {}

    def fake_ia(tema, tipo, base, pasta_imagens):
        chamado["ia"] = True
        return [(1, "frase um")]

    monkeypatch.setattr(pipeline, "_gerar_cenas_ia", fake_ia)
    monkeypatch.setattr(
        pipeline,
        "_gerar_cenas_personagem",
        lambda *a: pytest.fail("não deveria chamar personagem"),
    )

    gerar_video("tema", tipo, tmp_path / "out")
    assert chamado.get("ia") is True
