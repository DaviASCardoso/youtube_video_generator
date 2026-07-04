from types import SimpleNamespace

import pytest

from descoberta import gemini
from descoberta.gemini import AvaliacaoFit, avaliar_fit


def test_sem_chave_levanta_runtimeerror():
    with pytest.raises(RuntimeError):
        avaliar_fit("candidato", "prompt")


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
    avaliacao = AvaliacaoFit(aceito=True, score=82, tema="Foco", justificativa="cabe")
    monkeypatch.setattr(
        gemini.genai, "Client", _cliente_fake(SimpleNamespace(parsed=avaliacao))
    )
    resultado = avaliar_fit("candidato", "prompt")
    assert resultado.aceito is True
    assert resultado.score == 82
    assert resultado.tema == "Foco"


def test_fallback_para_text_quando_parsed_ausente(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    texto = '{"aceito": false, "score": 10, "tema": "Disciplina", "justificativa": "j"}'
    monkeypatch.setattr(
        gemini.genai,
        "Client",
        _cliente_fake(SimpleNamespace(parsed=None, text=texto)),
    )
    resultado = avaliar_fit("candidato", "prompt")
    assert resultado.aceito is False
    assert resultado.score == 10
    assert resultado.tema == "Disciplina"
