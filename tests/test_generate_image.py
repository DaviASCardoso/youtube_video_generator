import base64
import json
from types import SimpleNamespace

import pytest

from config.settings import Config
from geracao import generate_image
from geracao.generate_image import ASPECT_RATIOS, gerar_imagem


def _config(tmp_path, aspect="9:16"):
    caminho = tmp_path / "config.json"
    caminho.write_text(
        json.dumps({"together": {"modelo": "flux", "steps": 10, "aspect_ratio": aspect}}),
        encoding="utf-8",
    )
    return Config(caminho)


def _assets(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "style_prompt.txt").write_text("estilo cinematográfico", encoding="utf-8")
    return assets


def test_aspect_ratios_tem_9_16():
    assert ASPECT_RATIOS["9:16"] == (768, 1344)


class _ClienteFake:
    """Captura os kwargs e devolve uma imagem base64 fixa."""

    ultima_chamada = {}

    def __init__(self, *a, **k):
        pass

    @property
    def images(self):
        return self

    def generate(self, **kwargs):
        _ClienteFake.ultima_chamada = kwargs
        b64 = base64.b64encode(b"bytes-da-imagem").decode()
        return SimpleNamespace(data=[SimpleNamespace(b64_json=b64)])


def test_gerar_imagem_prepende_style_e_decodifica(tmp_path, monkeypatch):
    monkeypatch.setattr(generate_image, "Together", _ClienteFake)
    dados = gerar_imagem("um gato", _config(tmp_path), _assets(tmp_path))
    assert dados == b"bytes-da-imagem"
    assert _ClienteFake.ultima_chamada["prompt"] == "estilo cinematográfico um gato"
    assert _ClienteFake.ultima_chamada["width"] == 768


def test_gerar_imagem_aspect_invalido_levanta(tmp_path, monkeypatch):
    monkeypatch.setattr(generate_image, "Together", _ClienteFake)
    with pytest.raises(ValueError):
        gerar_imagem("x", _config(tmp_path, aspect="21:9"), _assets(tmp_path))


def test_gerar_imagem_referencia_inexistente_levanta(tmp_path, monkeypatch):
    monkeypatch.setattr(generate_image, "Together", _ClienteFake)
    with pytest.raises(FileNotFoundError):
        gerar_imagem(
            "x",
            _config(tmp_path),
            _assets(tmp_path),
            referencia=str(tmp_path / "nao_existe.png"),
        )
