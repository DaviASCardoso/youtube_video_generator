from types import SimpleNamespace

import pytest

from scripts import gemini
from scripts.gemini import TemaTendencia, gerar_tema_de_tendencia


def test_sem_chave_levanta_runtimeerror():
    with pytest.raises(RuntimeError):
        gerar_tema_de_tendencia("trend", "prompt")


def _cliente_fake(resposta):
    class _Cliente:
        def __init__(self, *a, **k):
            pass

        @property
        def models(self):
            return self

        def generate_content(self, **kwargs):
            return resposta

    return _Cliente


def test_retorna_parsed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    tema = TemaTendencia(tema="Foco", justificativa="porque sim")
    monkeypatch.setattr(
        gemini.genai, "Client", _cliente_fake(SimpleNamespace(parsed=tema))
    )
    resultado = gerar_tema_de_tendencia("trend", "prompt")
    assert resultado.tema == "Foco"


def test_fallback_para_text_quando_parsed_ausente(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    texto = '{"tema": "Disciplina", "justificativa": "j"}'
    monkeypatch.setattr(
        gemini.genai,
        "Client",
        _cliente_fake(SimpleNamespace(parsed=None, text=texto)),
    )
    resultado = gerar_tema_de_tendencia("trend", "prompt")
    assert resultado.tema == "Disciplina"
