import json

import pytest

from config.settings import Config
from scripts import generate_scene
from scripts.generate_scene import _normalizar, gerar_cenas


def test_normalizar_emocao_valida():
    assert _normalizar({"emocao": "Feliz", "busca": "office"}) == ("feliz", "office")


def test_normalizar_emocao_invalida_vira_neutro():
    emocao, _ = _normalizar({"emocao": "eufórico", "busca": "x"})
    assert emocao == "neutro"


def test_normalizar_busca_vazia_usa_fallback():
    _, busca = _normalizar({"emocao": "feliz", "busca": "  "})
    assert busca == "abstract textured background"


def test_normalizar_dict_vazio():
    assert _normalizar({}) == ("neutro", "abstract textured background")


def _config(tmp_path):
    caminho = tmp_path / "config.json"
    caminho.write_text(
        json.dumps(
            {
                "groq": {"modelo": "m", "temperatura": 0.7, "max_tokens": 100},
                "pipeline": {"min_chars_por_periodo": 10},
            }
        ),
        encoding="utf-8",
    )
    return Config(caminho)


def test_gerar_cenas_alinha_e_normaliza(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "system_prompt_script.txt").write_text("persona", encoding="utf-8")
    (assets / "system_prompt_cena.txt").write_text("instrucao", encoding="utf-8")

    respostas = iter(
        [
            "Frase um bem grande. Frase dois bem grande.",
            json.dumps(
                [
                    {"emocao": "feliz", "busca": "sunrise"},
                    {"emocao": "invalida", "busca": ""},
                ]
            ),
        ]
    )
    monkeypatch.setattr(generate_scene, "_chamar_api", lambda *a, **k: next(respostas))

    cenas = gerar_cenas("tema", _config(tmp_path), assets)
    assert len(cenas) == 2
    assert cenas[0] == (1, "Frase um bem grande.", "feliz", "sunrise")
    # segunda cena caiu nos fallbacks
    assert cenas[1] == (2, "Frase dois bem grande.", "neutro", "abstract textured background")


def test_gerar_cenas_menos_decisoes_que_frases(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "system_prompt_script.txt").write_text("persona", encoding="utf-8")
    (assets / "system_prompt_cena.txt").write_text("instrucao", encoding="utf-8")

    respostas = iter(
        [
            "Frase um bem grande. Frase dois bem grande.",
            json.dumps([{"emocao": "feliz", "busca": "sunrise"}]),  # só uma decisão
        ]
    )
    monkeypatch.setattr(generate_scene, "_chamar_api", lambda *a, **k: next(respostas))

    cenas = gerar_cenas("tema", _config(tmp_path), assets)
    # ainda 1:1 com as frases; a frase sem decisão usa fallback em vez de quebrar
    assert len(cenas) == 2
    assert cenas[1][2:] == ("neutro", "abstract textured background")
