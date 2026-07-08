import json

import pytest

from config.settings import Config
from geracao import generate_scene
from geracao.custo import Ledger
from geracao.generate_scene import _normalizar, gerar_cenas, planejar_emocoes


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


def test_planejar_emocoes_uma_por_frase(tmp_path, monkeypatch):
    # A camada de personagem planeja só a emoção (ignora a busca), 1:1 com as frases.
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "system_prompt_cena.txt").write_text("instrucao", encoding="utf-8")

    monkeypatch.setattr(
        generate_scene, "_chamar_api",
        lambda *a, **k: json.dumps([
            {"emocao": "feliz", "busca": "ignorada"},
            {"emocao": "invalida", "busca": "x"},  # -> neutro
        ]),
    )
    led = Ledger()
    emocoes = planejar_emocoes([(1, "Frase um."), (2, "Frase dois.")], _config(tmp_path), assets, ledger=led)
    assert emocoes == ["feliz", "neutro"]
    assert led.provedores()["plano_personagem"] == "groq"


def test_planejar_emocoes_menos_decisoes_que_frases(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "system_prompt_cena.txt").write_text("instrucao", encoding="utf-8")

    monkeypatch.setattr(
        generate_scene, "_chamar_api",
        lambda *a, **k: json.dumps([{"emocao": "serio", "busca": "x"}]),  # só uma
    )
    emocoes = planejar_emocoes([(1, "a"), (2, "b"), (3, "c")], _config(tmp_path), assets)
    assert emocoes == ["serio", "neutro", "neutro"]  # 1:1, resto no fallback


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
