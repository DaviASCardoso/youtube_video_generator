from descoberta import fit
from descoberta.candidato import Candidato, agora
from descoberta.configuracao import DESCOBERTA_PADRAO
from descoberta.gemini import AvaliacaoFit


def _cand(texto="algo"):
    return Candidato(texto=texto, fonte="reddit", forca_sinal=0.5, observado_em=agora())


def test_avaliar_preenche_e_aceita(monkeypatch, make_tipo):
    tipo = make_tipo()
    monkeypatch.setattr(
        fit.gemini,
        "avaliar_fit",
        lambda cand, prompt: AvaliacaoFit(aceito=True, score=80, tema="Tema X", justificativa="j"),
    )
    c = _cand()
    passou = fit.avaliar(c, tipo, DESCOBERTA_PADRAO)
    assert passou is True
    assert c.fit_score == 80.0
    assert c.tema == "Tema X"
    assert c.justificativa == "j"


def test_avaliar_reprova_abaixo_do_minimo(monkeypatch, make_tipo):
    tipo = make_tipo()
    monkeypatch.setattr(
        fit.gemini,
        "avaliar_fit",
        lambda cand, prompt: AvaliacaoFit(aceito=True, score=40, tema="T", justificativa="j"),
    )
    c = _cand()
    # score_minimo padrão = 60
    assert fit.avaliar(c, tipo, DESCOBERTA_PADRAO) is False
    assert c.fit_score == 40.0  # preencheu mesmo reprovando


def test_avaliar_respeita_aceito_false(monkeypatch, make_tipo):
    tipo = make_tipo()
    monkeypatch.setattr(
        fit.gemini,
        "avaliar_fit",
        lambda cand, prompt: AvaliacaoFit(aceito=False, score=90, tema="T", justificativa="j"),
    )
    # modelo disse não, mesmo com score alto
    assert fit.avaliar(_cand(), tipo, DESCOBERTA_PADRAO) is False
