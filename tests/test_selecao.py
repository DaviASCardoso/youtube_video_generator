from datetime import datetime, timedelta, timezone

from descoberta import selecao
from descoberta.candidato import Candidato

_CFG = {"peso_sinal": 0.4, "peso_fit": 0.4, "peso_frescor": 0.2, "meia_vida_horas": 48}
_AGORA = datetime(2026, 7, 4, 12, tzinfo=timezone.utc)


def _cand(texto, forca=0.5, fit=None, idade_h=0.0):
    return Candidato(
        texto=texto,
        fonte="x",
        forca_sinal=forca,
        observado_em=_AGORA - timedelta(hours=idade_h),
        fit_score=fit,
    )


def test_frescor_recente_vale_um():
    assert selecao.frescor(_AGORA, _AGORA, 48) == 1.0


def test_frescor_meia_vida():
    meio = selecao.frescor(_AGORA - timedelta(hours=48), _AGORA, 48)
    assert abs(meio - 0.5) < 1e-9


def test_pontuar_combina_pesos():
    c = _cand("t", forca=1.0, fit=100, idade_h=0.0)
    # 0.4*1 + 0.4*1 + 0.2*1 = 1.0
    assert abs(selecao.pontuar(c, _CFG, _AGORA) - 1.0) < 1e-9


def test_selecionar_prefere_maior_pontuacao():
    forte = _cand("forte", forca=1.0, fit=90)
    fraco = _cand("fraco", forca=0.1, fit=20)
    melhor, pont = selecao.selecionar([fraco, forte], _CFG, _AGORA)
    assert melhor.texto == "forte"
    assert pont > 0


def test_selecionar_frescor_desempata():
    novo = _cand("novo", forca=0.5, fit=80, idade_h=0.0)
    velho = _cand("velho", forca=0.5, fit=80, idade_h=240.0)  # bem mais velho
    melhor, _ = selecao.selecionar([velho, novo], _CFG, _AGORA)
    assert melhor.texto == "novo"


def test_selecionar_vazio():
    assert selecao.selecionar([], _CFG, _AGORA) == (None, 0.0)
