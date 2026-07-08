import json

import conformidade.autenticidade as aut
from conformidade.autenticidade import verificar_autenticidade

_CFG = {"variacao_minima": 0.25, "teto_sameness": 70, "n_recentes": 5}
_PERSONA = "Você é o Cético Prático, um narrador seco e direto ao ponto."


class _ConfigFake:
    def get(self, chave):
        return {"groq.modelo": "m", "groq.temperatura": 0.5, "groq.max_tokens": 100}.get(chave)


def _mock_sameness(monkeypatch, valor, motivo=""):
    monkeypatch.setattr(aut, "_chamar_api", lambda s, u, c: json.dumps({"sameness": valor, "motivo": motivo}))


def test_default_saudavel_nao_sinaliza(monkeypatch):
    _mock_sameness(monkeypatch, 30)
    r = verificar_autenticidade("roteiro novo", ["r1", "r2"], 0.3, _PERSONA, _CFG, _ConfigFake())
    assert r["flag"] is False
    assert r["variacao_ok"] and r["persona_ok"]
    assert r["sameness"] == 30


def test_variacao_insuficiente_sinaliza(monkeypatch):
    _mock_sameness(monkeypatch, 10)
    r = verificar_autenticidade("x", ["r1"], 0.1, _PERSONA, _CFG, _ConfigFake())
    assert r["flag"] is True
    assert r["variacao_ok"] is False
    assert any("variação" in m for m in r["motivos"])


def test_persona_ausente_sinaliza(monkeypatch):
    _mock_sameness(monkeypatch, 10)
    r = verificar_autenticidade("x", ["r1"], 0.3, "", _CFG, _ConfigFake())
    assert r["flag"] is True
    assert r["persona_ok"] is False


def test_sameness_acima_do_teto_sinaliza(monkeypatch):
    _mock_sameness(monkeypatch, 88, motivo="mesma abertura")
    r = verificar_autenticidade("x", ["r1", "r2"], 0.3, _PERSONA, _CFG, _ConfigFake())
    assert r["flag"] is True
    assert r["sameness"] == 88
    assert any("sameness" in m for m in r["motivos"])


def test_sem_recentes_nao_computa_sameness(monkeypatch):
    def nao_deveria(s, u, c):
        raise AssertionError("não deveria chamar Groq sem recentes")

    monkeypatch.setattr(aut, "_chamar_api", nao_deveria)
    r = verificar_autenticidade("x", [], 0.3, _PERSONA, _CFG, _ConfigFake())
    assert r["sameness"] is None
    assert r["flag"] is False


def test_groq_falha_aberto(monkeypatch):
    def boom(s, u, c):
        raise RuntimeError("sem chave")

    monkeypatch.setattr(aut, "_chamar_api", boom)
    r = verificar_autenticidade("x", ["r1"], 0.3, _PERSONA, _CFG, _ConfigFake())
    assert r["sameness"] is None
    assert r["flag"] is False  # objetivo ok + sameness não computado → sem sinal


def test_n_recentes_limita(monkeypatch):
    visto = {}

    def captura(s, u, c):
        visto["user"] = u
        return json.dumps({"sameness": 10})

    monkeypatch.setattr(aut, "_chamar_api", captura)
    verificar_autenticidade("novo", ["a", "b", "c", "d"], 0.3, _PERSONA, {**_CFG, "n_recentes": 2}, _ConfigFake())
    # só os 2 primeiros recentes entram no prompt
    assert "a" in visto["user"] and "b" in visto["user"]
    assert "c" not in visto["user"].split("ROTEIROS RECENTES")[-1]
