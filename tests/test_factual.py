import json

import conformidade.factual as factual
from conformidade.factual import verificar_factual


class _ConfigFake:
    def get(self, chave):
        return {"groq.modelo": "m", "groq.temperatura": 0.5, "groq.max_tokens": 100}.get(chave)


def test_alegacoes_falsas_sinalizam(monkeypatch):
    monkeypatch.setattr(
        factual, "_chamar_api",
        lambda s, u, c: json.dumps({"alegacoes_falsas": ["a Terra é plana", "vitamina C cura gripe"]}),
    )
    r = verificar_factual("roteiro com afirmações", _ConfigFake())
    assert r["flag"] is True
    assert len(r["alegacoes"]) == 2


def test_sem_alegacoes_nao_sinaliza(monkeypatch):
    monkeypatch.setattr(factual, "_chamar_api", lambda s, u, c: json.dumps({"alegacoes_falsas": []}))
    r = verificar_factual("roteiro correto", _ConfigFake())
    assert r["flag"] is False
    assert r["alegacoes"] == []


def test_alegacoes_vazias_sao_filtradas(monkeypatch):
    monkeypatch.setattr(factual, "_chamar_api", lambda s, u, c: json.dumps({"alegacoes_falsas": ["", "  ", "real"]}))
    r = verificar_factual("x", _ConfigFake())
    assert r["alegacoes"] == ["real"]


def test_groq_falha_aberto(monkeypatch):
    def boom(s, u, c):
        raise RuntimeError("sem chave")

    monkeypatch.setattr(factual, "_chamar_api", boom)
    r = verificar_factual("x", _ConfigFake())
    assert r == {"flag": False, "alegacoes": []}
