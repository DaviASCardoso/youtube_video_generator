import json

import pytest

from config.settings import Config
from scripts import generate_script
from scripts.generate_script import _parsear_prompts, _separar_periodos, gerar_roteiro


def test_separar_periodos_junta_curtos():
    texto = "Primeira parte bem longa que ja passou. Segunda. Terceira parte tambem bem longa."
    frases = _separar_periodos(texto, min_chars=20)
    # o 1º período já passa do mínimo e fecha; "Segunda." é curto e absorve o próximo
    assert frases == [
        "Primeira parte bem longa que ja passou.",
        "Segunda. Terceira parte tambem bem longa.",
    ]


def test_separar_periodos_ultimo_curto_gruda_no_anterior():
    texto = "Primeira frase bem longa que passa do limite mínimo. Fim."
    frases = _separar_periodos(texto, min_chars=20)
    # "Fim." é curto e cola no período anterior em vez de virar frase própria
    assert frases == ["Primeira frase bem longa que passa do limite mínimo. Fim."]


def test_separar_periodos_ignora_vazios():
    assert _separar_periodos("   ", min_chars=10) == []


def test_parsear_prompts_remove_cerca_json():
    resposta = '```json\n["a", "b", "c"]\n```'
    assert _parsear_prompts(resposta) == ["a", "b", "c"]


def test_parsear_prompts_sem_cerca():
    assert _parsear_prompts('["x"]') == ["x"]


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


def test_gerar_roteiro_frases_e_prompts_1_para_1(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "system_prompt_script.txt").write_text("persona", encoding="utf-8")
    (assets / "system_prompt_prompt.txt").write_text("instrucao", encoding="utf-8")

    # duas chamadas: primeiro o roteiro, depois os prompts de imagem em JSON
    respostas = iter(
        [
            "Frase um bem grande. Frase dois bem grande.",
            '["prompt 1", "prompt 2"]',
        ]
    )
    monkeypatch.setattr(
        generate_script, "_chamar_api", lambda *a, **k: next(respostas)
    )

    frases, prompts = gerar_roteiro("tema", _config(tmp_path), assets)
    assert len(frases) == len(prompts) == 2
    assert frases[0] == (1, "Frase um bem grande.")
    assert prompts[1] == (2, "prompt 2")
