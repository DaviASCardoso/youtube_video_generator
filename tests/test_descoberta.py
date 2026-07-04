import pytest

from descoberta import descoberta as orq
from descoberta import estado
from descoberta.candidato import Candidato, agora


def _c(texto, forca=0.5, categoria="trending", fit=None):
    return Candidato(
        texto=texto,
        fonte="reddit",
        forca_sinal=forca,
        observado_em=agora(),
        categoria=categoria,
        fit_score=fit,
    )


@pytest.fixture
def isolar(monkeypatch):
    """Isola o orquestrador do store real de tendências (pasta tendencias/)."""
    monkeypatch.setattr(orq.dedup, "sinais_recentes", lambda tipo, dias: set())

    class _HistFake:
        def registrar(self, *a, **k):
            return None

    monkeypatch.setattr(orq, "historico_tendencias", _HistFake())


def _aprovar_todos(monkeypatch, score=80.0):
    def _av(c, tipo, cfg):
        c.fit_score = score
        c.tema = f"Tema: {c.texto}"
        c.justificativa = "j"
        return True

    monkeypatch.setattr(orq.fit, "avaliar", _av)


def test_decide_e_grava_slot(make_tipo, monkeypatch, isolar):
    tipo = make_tipo()
    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([_c("Ideia A", 0.9), _c("Ideia B", 0.4)], {"reddit": 2}))
    _aprovar_todos(monkeypatch)

    d = orq.decidir_tema(tipo)
    assert d is not None
    assert d.estado == "pronto"
    assert d.tema == "Tema: Ideia A"  # maior força vence
    assert estado.slot_de(tipo).ler().tema == d.tema


def test_gate_revisar_deixa_pendente(make_tipo, monkeypatch, isolar):
    tipo = make_tipo(config_extra={"descoberta": {"modo_revisao": "revisar"}})
    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([_c("A")], {}))
    _aprovar_todos(monkeypatch)

    d = orq.decidir_tema(tipo)
    assert d.estado == "pendente"
    assert estado.slot_de(tipo).ler().estado == "pendente"


def test_orcamento_limita_avaliacoes(make_tipo, monkeypatch, isolar):
    tipo = make_tipo()  # orcamento_avaliacao padrão = 3
    cands = [_c(f"C{i}", forca=1.0 - i * 0.1) for i in range(5)]
    monkeypatch.setattr(orq, "_coletar", lambda t, c: (cands, {}))

    chamadas = []

    def _av(c, tipo, cfg):
        chamadas.append(c.texto)
        c.fit_score = 70.0
        c.tema = c.texto
        return True

    monkeypatch.setattr(orq.fit, "avaliar", _av)
    orq.decidir_tema(tipo)
    assert len(chamadas) == 3


def test_retido_nao_reavaliado(make_tipo, monkeypatch, isolar):
    tipo = make_tipo(config_extra={"descoberta": {"retencao": "reter"}})
    retido = _c("Retido", forca=0.9, fit=85.0)
    retido.tema = "Tema Retido"
    retido.justificativa = "j"
    estado.buffer_de(tipo).substituir([retido])

    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([], {}))
    chamadas = []
    monkeypatch.setattr(orq.fit, "avaliar", lambda c, t, cfg: chamadas.append(c.texto) or True)

    d = orq.decidir_tema(tipo)
    assert chamadas == []  # não reavaliou o retido
    assert d.tema == "Tema Retido"


def test_descartar_limpa_buffer(make_tipo, monkeypatch, isolar):
    tipo = make_tipo()  # retencao padrão = descartar
    velho = _c("Velho", fit=80.0)
    estado.buffer_de(tipo).substituir([velho])

    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([_c("Novo")], {}))
    _aprovar_todos(monkeypatch)

    orq.decidir_tema(tipo)
    assert estado.buffer_de(tipo).listar() == []


def test_reter_guarda_nao_escolhidos(make_tipo, monkeypatch, isolar):
    tipo = make_tipo(config_extra={"descoberta": {"retencao": "reter"}})
    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([_c("Vencedor", 0.9), _c("Perdedor", 0.1)], {}))
    _aprovar_todos(monkeypatch)

    d = orq.decidir_tema(tipo)
    retidos = estado.buffer_de(tipo).listar()
    assert d.tema == "Tema: Vencedor"
    assert [c.texto for c in retidos] == ["Perdedor"]


def test_nenhum_aprovado_retorna_none(make_tipo, monkeypatch, isolar):
    tipo = make_tipo()
    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([_c("X")], {}))
    monkeypatch.setattr(orq.fit, "avaliar", lambda c, t, cfg: False)

    d = orq.decidir_tema(tipo)
    assert d is None
    assert estado.slot_de(tipo).ler() is None


def test_sem_candidatos_retorna_none(make_tipo, monkeypatch, isolar):
    tipo = make_tipo()
    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([], {}))
    d = orq.decidir_tema(tipo)
    assert d is None


def test_dry_run_nao_grava(make_tipo, monkeypatch, isolar):
    tipo = make_tipo()
    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([_c("A")], {}))
    _aprovar_todos(monkeypatch)

    d = orq.decidir_tema(tipo, persistir=False)
    assert d is not None
    assert estado.slot_de(tipo).ler() is None
    assert estado.historico_de(tipo).listar() == []
