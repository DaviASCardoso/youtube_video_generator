from datetime import datetime, timedelta, timezone

from descoberta import estado
from descoberta.candidato import Candidato, Decisao, agora


def _decisao(estado_gate="pronto", tema="Tema"):
    return Decisao(
        tema=tema,
        fonte="reddit",
        categoria="trending",
        fit_score=80.0,
        justificativa="j",
        prioridade=0.6,
        estado=estado_gate,
    )


def test_slot_vazio_le_none(make_tipo):
    assert estado.slot_de(make_tipo()).ler() is None


def test_slot_gravar_ler(make_tipo):
    s = estado.slot_de(make_tipo())
    d = _decisao("pendente")
    s.gravar(d)
    assert s.ler() == d


def test_slot_aprovar_marca_pronto(make_tipo):
    s = estado.slot_de(make_tipo())
    s.gravar(_decisao("pendente"))
    aprovada = s.aprovar()
    assert aprovada.estado == "pronto"
    assert s.ler().estado == "pronto"


def test_slot_aprovar_vazio(make_tipo):
    assert estado.slot_de(make_tipo()).aprovar() is None


def test_slot_limpar(make_tipo):
    s = estado.slot_de(make_tipo())
    s.gravar(_decisao())
    s.limpar()
    assert s.ler() is None


def test_buffer_roundtrip(make_tipo):
    b = estado.buffer_de(make_tipo())
    assert b.listar() == []
    c = Candidato("t", "reddit", 0.5, agora(), fit_score=70.0)
    b.substituir([c])
    out = b.listar()
    assert len(out) == 1 and out[0].fit_score == 70.0
    b.limpar()
    assert b.listar() == []


def test_historico_categorias_recentes(make_tipo):
    h = estado.historico_de(make_tipo())
    h.registrar({"decidido": {"categoria": "trending", "tema": "A"}})
    h.registrar({"decidido": {"categoria": "evergreen", "tema": "B"}})
    assert h.categorias_recentes(10) == ["evergreen", "trending"]  # recente primeiro
    assert h.categorias_recentes(1) == ["evergreen"]


def test_historico_ignora_sem_decidido(make_tipo):
    h = estado.historico_de(make_tipo())
    h.registrar({"decidido": None, "motivo": "nenhum_aprovado"})
    assert h.categorias_recentes(10) == []


def test_temas_decididos_recentes_normaliza(make_tipo):
    h = estado.historico_de(make_tipo())
    h.registrar({"decidido": {"categoria": "trending", "tema": "Foco Total"}})
    assert "foco total" in h.temas_decididos_recentes(14)


def test_temas_decididos_respeita_janela(make_tipo):
    h = estado.historico_de(make_tipo())
    h.registrar({"decidido": {"categoria": "trending", "tema": "Antigo"}})
    dados = h.listar()
    dados[0]["quando"] = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    h._salvar(dados)
    assert h.temas_decididos_recentes(14) == set()
