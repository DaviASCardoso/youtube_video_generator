from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from feedback import ingestao
from feedback.armazenamento import metricas_de
from feedback.configuracao import mesclar_feedback

AGORA = datetime(2026, 7, 3, tzinfo=timezone.utc)  # 48h após publicar
PUB = "2026-07-01T00:00:00+00:00"

FEEDBACK_ON = mesclar_feedback({"destinos": {"youtube": {"ativo": True}}})


def _registros(status="publicado", vid="vidA", destino="youtube"):
    return [
        {
            "id": "exec1",
            "tipo_id": "tipo_teste",
            "tema": "Foco no essencial",
            "finalizado_em": PUB,
            "publicacao": [{"destino": destino, "id": vid, "url": "u", "status": status}],
        }
    ]


class _FakeDestino:
    def __init__(self, dados):
        self.dados = dados
        self.chamadas = []

    def metricas_do_video(self, tipo, video_id, publicado_em, chaves=None):
        self.chamadas.append(video_id)
        return self.dados


def _wire(monkeypatch, registros, destino):
    import operacoes.execucoes as ex

    monkeypatch.setattr(ex, "historico", SimpleNamespace(listar=lambda tid: registros))
    monkeypatch.setattr(ingestao.destinos, "obter", lambda nome: destino)


@pytest.fixture
def tipo_on(make_tipo):
    return make_tipo("tipo_teste", config_extra={"feedback": FEEDBACK_ON})


# --- destino desligado (pilar inerte) ---------------------------------------


def test_destino_off_pula_tudo(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")  # feedback default => youtube off
    _wire(monkeypatch, _registros(), _FakeDestino({"avg_view_pct": 50}))
    r = ingestao.ingerir(tipo, agora=AGORA)
    assert r["pulado"] == "destinos_desligados"


# --- coleta e persistência --------------------------------------------------


def test_coleta_e_grava_snapshot(tipo_on, monkeypatch):
    destino = _FakeDestino({"avg_view_pct": 55.0, "curva": [[0.0, 1.0]]})
    _wire(monkeypatch, _registros(), destino)

    r = ingestao.ingerir(tipo_on, agora=AGORA)
    assert r["polados"] == ["vidA"]

    reg = metricas_de(tipo_on).video("vidA")
    assert reg["polls"]["24"]["avg_view_pct"] == 55.0
    assert reg["polls"]["24"]["marco"] == 24
    assert reg["ultimo_marco"] == 24
    assert reg["tema"] == "Foco no essencial"
    assert reg["destino"] == "youtube"


def test_nao_repuxa_marco_ja_coletado(tipo_on, monkeypatch):
    destino = _FakeDestino({"avg_view_pct": 55.0})
    _wire(monkeypatch, _registros(), destino)
    ingestao.ingerir(tipo_on, agora=AGORA)  # coleta o marco 24
    destino.chamadas.clear()
    r2 = ingestao.ingerir(tipo_on, agora=AGORA)  # mesma janela: nada devido
    assert destino.chamadas == []  # nenhuma chamada de API
    assert r2["ignorados"] == ["vidA"]


def test_marco_maior_marca_todos_devidos(tipo_on, monkeypatch):
    destino = _FakeDestino({"avg_view_pct": 60.0})
    _wire(monkeypatch, _registros(), destino)
    agora_100h = datetime(2026, 7, 5, 4, tzinfo=timezone.utc)  # 100h => 24 e 72 devidos
    ingestao.ingerir(tipo_on, agora=agora_100h)
    reg = metricas_de(tipo_on).video("vidA")
    assert set(reg["polls"].keys()) == {"24", "72"}
    assert reg["ultimo_marco"] == 72
    assert len(destino.chamadas) == 1  # uma consulta cobre os dois marcos


# --- degradação -------------------------------------------------------------


def test_metricas_none_mantem_ultimo_bom(tipo_on, monkeypatch):
    destino = _FakeDestino(None)  # falha de coleta
    _wire(monkeypatch, _registros(), destino)
    r = ingestao.ingerir(tipo_on, agora=AGORA)
    assert r["falhas"] == ["vidA"]
    assert metricas_de(tipo_on).video("vidA") is None  # nada gravado


def test_destino_que_levanta_degrada(tipo_on, monkeypatch):
    class _Boom:
        def metricas_do_video(self, *a, **k):
            raise RuntimeError("estourou")

    _wire(monkeypatch, _registros(), _Boom())
    r = ingestao.ingerir(tipo_on, agora=AGORA)
    assert r["falhas"] == ["vidA"]


# --- filtros de published-record --------------------------------------------


def test_ignora_status_nao_publicado(tipo_on, monkeypatch):
    destino = _FakeDestino({"avg_view_pct": 1})
    _wire(monkeypatch, _registros(status="erro"), destino)
    r = ingestao.ingerir(tipo_on, agora=AGORA)
    assert r["polados"] == [] and destino.chamadas == []


def test_ignora_destino_sem_id(tipo_on, monkeypatch):
    registros = [{"id": "e", "tema": "t", "finalizado_em": PUB,
                  "publicacao": [{"destino": "youtube", "status": "publicado"}]}]
    destino = _FakeDestino({"avg_view_pct": 1})
    _wire(monkeypatch, registros, destino)
    r = ingestao.ingerir(tipo_on, agora=AGORA)
    assert r["polados"] == []


def test_usa_agendado_para_quando_presente(tipo_on, monkeypatch):
    registros = [{
        "id": "e", "tema": "t", "finalizado_em": "2026-06-01T00:00:00+00:00",
        "publicacao": [{"destino": "youtube", "id": "vidX", "status": "agendado",
                        "agendado_para": PUB}],
    }]
    destino = _FakeDestino({"avg_view_pct": 42})
    _wire(monkeypatch, registros, destino)
    ingestao.ingerir(tipo_on, agora=AGORA)  # 48h após agendado_para
    reg = metricas_de(tipo_on).video("vidX")
    assert reg["publicado_em"] == PUB
    assert reg["polls"]["24"]["avg_view_pct"] == 42
