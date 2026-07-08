import json

import conformidade.marca as marca
from conformidade.marca import avaliar_tema
from conformidade.regras import REGRAS_PADRAO


class _ConfigFake:
    def get(self, chave):
        return {"groq.modelo": "m", "groq.temperatura": 0.5, "groq.max_tokens": 100}.get(chave)


def _mock_groq(monkeypatch, apropriado=True, motivo=""):
    monkeypatch.setattr(
        marca, "_chamar_api",
        lambda s, u, c: json.dumps({"apropriado": apropriado, "motivo": motivo}),
    )


def test_termo_de_bloqueio_bloqueia_em_equilibrada(monkeypatch):
    _mock_groq(monkeypatch)
    v = avaliar_tema("como lidar com pensamentos de suicídio", "equilibrada", REGRAS_PADRAO, _ConfigFake())
    assert v.bloqueado is True
    assert "suicídio" in v.motivo


def test_termo_de_bloqueio_vira_flag_em_advisory(monkeypatch):
    _mock_groq(monkeypatch)
    v = avaliar_tema("massacre na história", "advisory", REGRAS_PADRAO, _ConfigFake())
    assert v.sinalizado is True


def test_termo_sensivel_sinaliza_em_equilibrada(monkeypatch):
    _mock_groq(monkeypatch)
    v = avaliar_tema("como lidar com a morte de um pet", "equilibrada", REGRAS_PADRAO, _ConfigFake())
    assert v.sinalizado is True
    assert "sensível" in v.motivo


def test_termo_sensivel_bloqueia_em_modo_bloquear(monkeypatch):
    _mock_groq(monkeypatch)
    v = avaliar_tema("superando um vício", "bloquear", REGRAS_PADRAO, _ConfigFake())
    assert v.bloqueado is True


def test_groq_limitrofe_sinaliza(monkeypatch):
    _mock_groq(monkeypatch, apropriado=False, motivo="tema politicamente sensível")
    v = avaliar_tema("produtividade sem drama", "equilibrada", REGRAS_PADRAO, _ConfigFake())
    assert v.sinalizado is True
    assert "politicamente sensível" in v.motivo


def test_tema_limpo_liberado(monkeypatch):
    _mock_groq(monkeypatch, apropriado=True)
    v = avaliar_tema("como organizar a rotina da manhã", "equilibrada", REGRAS_PADRAO, _ConfigFake())
    assert v.resultado == "liberado"


def test_groq_falha_aberto(monkeypatch):
    def boom(s, u, c):
        raise RuntimeError("sem chave")

    monkeypatch.setattr(marca, "_chamar_api", boom)
    # sem lista batida e Groq falhando → liberado (a camada objetiva não dependeu do LLM)
    v = avaliar_tema("dicas de foco", "equilibrada", REGRAS_PADRAO, _ConfigFake())
    assert v.resultado == "liberado"


def test_bloqueio_dispensa_o_groq(monkeypatch):
    def nao_deveria(s, u, c):
        raise AssertionError("Groq não deveria ser chamado num bloqueio clear-cut")

    monkeypatch.setattr(marca, "_chamar_api", nao_deveria)
    v = avaliar_tema("um relato de tortura", "equilibrada", REGRAS_PADRAO, _ConfigFake())
    assert v.bloqueado is True
