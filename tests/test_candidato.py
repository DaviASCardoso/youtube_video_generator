from datetime import datetime, timezone

from descoberta.candidato import Candidato, Decisao, agora, forca_por_posicao


def test_forca_por_posicao_topo_vale_um():
    assert forca_por_posicao(0, 10) == 1.0


def test_forca_por_posicao_cai_com_a_posicao():
    assert forca_por_posicao(0, 5) > forca_por_posicao(4, 5) > 0


def test_forca_por_posicao_total_zero():
    assert forca_por_posicao(0, 0) == 0.0


def test_agora_e_utc():
    assert agora().tzinfo == timezone.utc


def test_candidato_roundtrip():
    c = Candidato(
        texto="tema",
        fonte="reddit",
        forca_sinal=0.7,
        observado_em=datetime(2026, 7, 4, tzinfo=timezone.utc),
        categoria="evergreen",
        fit_score=80.0,
        justificativa="j",
        tema="Tema pronto",
    )
    restaurado = Candidato.de_dict(c.para_dict())
    assert restaurado == c


def test_candidato_de_dict_defaults():
    c = Candidato.de_dict(
        {
            "texto": "t",
            "fonte": "f",
            "forca_sinal": 0.5,
            "observado_em": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        }
    )
    assert c.categoria == "trending"
    assert c.fit_score is None


def test_decisao_roundtrip():
    d = Decisao(
        tema="Tema",
        fonte="trends_mcp",
        categoria="trending",
        fit_score=75.0,
        justificativa="cabe no canal",
        prioridade=0.62,
        estado="pendente",
    )
    assert Decisao.de_dict(d.para_dict()) == d
