from collections import namedtuple
from types import SimpleNamespace

import pytest

from operacoes import saude
from operacoes import notificacoes

_Uso = namedtuple("_Uso", "total used free")


# --- disco -------------------------------------------------------------------


def test_disco_marca_baixo(monkeypatch, tmp_path):
    gb = 1024 ** 3
    monkeypatch.setattr(saude.shutil, "disk_usage", lambda p: _Uso(100 * gb, 95 * gb, 5 * gb))
    d = saude.disco(str(tmp_path), limite_pct=10.0)
    assert d["livre_pct"] == 5.0
    assert d["baixo"] is True
    assert d["livre_gb"] == 5.0


def test_disco_ok(monkeypatch, tmp_path):
    gb = 1024 ** 3
    monkeypatch.setattr(saude.shutil, "disk_usage", lambda p: _Uso(100 * gb, 20 * gb, 80 * gb))
    d = saude.disco(str(tmp_path), limite_pct=10.0)
    assert d["baixo"] is False
    assert d["livre_pct"] == 80.0


def test_disco_sobe_para_pasta_existente(monkeypatch, tmp_path):
    # a pasta de saída pode não existir ainda; deve subir até um ancestral
    gb = 1024 ** 3
    capturado = {}

    def _fake(p):
        capturado["p"] = str(p)
        return _Uso(10 * gb, 1 * gb, 9 * gb)

    monkeypatch.setattr(saude.shutil, "disk_usage", _fake)
    inexistente = tmp_path / "nao" / "existe" / "ainda"
    saude.disco(str(inexistente))
    assert capturado["p"] == str(tmp_path)  # subiu até o ancestral existente


# --- scheduler ---------------------------------------------------------------


def test_scheduler_rodando(monkeypatch):
    from operacoes import scheduler as sched_mod

    monkeypatch.setattr(sched_mod, "scheduler", SimpleNamespace(running=True))
    assert saude.scheduler_rodando() is True
    monkeypatch.setattr(sched_mod, "scheduler", SimpleNamespace(running=False))
    assert saude.scheduler_rodando() is False


def test_heartbeat_fresco(tmp_path):
    from datetime import datetime, timedelta, timezone

    caminho = tmp_path / "hb.json"
    agora = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    saude.registrar_heartbeat(agora=agora, caminho=caminho)
    hb = saude.heartbeat(agora=agora + timedelta(hours=1), caminho=caminho)
    assert hb["idade_seg"] == 3600.0
    assert hb["estagnado"] is False


def test_heartbeat_estagnado(tmp_path):
    from datetime import datetime, timedelta, timezone

    caminho = tmp_path / "hb.json"
    agora = datetime(2026, 7, 7, 0, 0, tzinfo=timezone.utc)
    saude.registrar_heartbeat(agora=agora, caminho=caminho)
    hb = saude.heartbeat(agora=agora + timedelta(hours=14), caminho=caminho)
    assert hb["estagnado"] is True


def test_heartbeat_ausente_nao_alarma(tmp_path):
    hb = saude.heartbeat(caminho=tmp_path / "inexistente.json")
    assert hb == {"quando": None, "idade_seg": None, "estagnado": False}


# --- custo / orçamento / cota -----------------------------------------------


def test_gasto_hoje(monkeypatch):
    import geracao.custo as custo

    monkeypatch.setattr(custo, "gasto_diario", SimpleNamespace(gasto_hoje=lambda: 1.234567))
    assert saude.gasto_hoje() == 1.234567


def test_orcamento_do_tipo(make_tipo):
    tipo = make_tipo()
    assert saude.orcamento_do_tipo(tipo) == 10.0  # default por_dia_usd


def test_cota_do_tipo(make_tipo, monkeypatch):
    import publicacao.quota as quota

    monkeypatch.setattr(quota, "quota_diaria", SimpleNamespace(uploads_hoje=lambda cred: 2))
    tipo = make_tipo()
    c = saude.cota_do_tipo(tipo)
    assert c["uploads"] == 2
    assert c["cap"] == 5  # default cap_diario


# --- credenciais -------------------------------------------------------------


def test_credenciais_so_checa_quem_publica(make_tipo, monkeypatch):
    from publicacao import youtube

    inativo = make_tipo(id_tipo="inativo")  # sem destino ativo
    ativo = make_tipo(
        id_tipo="ativo",
        config_extra={"publicacao": {"destinos": {"youtube": {"ativo": True}}}},
    )
    monkeypatch.setattr(
        youtube, "checar_credencial",
        lambda tipo: {"status": "expirando", "detalhe": "7 dias"},
    )
    res = saude.credenciais([inativo, ativo])
    assert [c["tipo_id"] for c in res] == ["ativo"]
    assert res[0]["status"] == "expirando"


def test_credenciais_degrada_em_erro(make_tipo, monkeypatch):
    from publicacao import youtube

    ativo = make_tipo(config_extra={"publicacao": {"destinos": {"youtube": {"ativo": True}}}})

    def _boom(tipo):
        raise RuntimeError("api caiu")

    monkeypatch.setattr(youtube, "checar_credencial", _boom)
    res = saude.credenciais([ativo])
    assert res[0]["status"] == "erro"


# --- último publish ----------------------------------------------------------


def test_ultimo_publish(monkeypatch, make_tipo):
    import operacoes.execucoes as ex

    tipo = make_tipo()
    registros = [
        {"iniciado_em": "2026-07-05T10:00:00Z", "finalizado_em": "2026-07-05T10:05:00Z",
         "publicacao": [{"destino": "youtube", "status": "publicado", "url": "https://youtu.be/A"}]},
        {"iniciado_em": "2026-07-04T10:00:00Z", "publicacao": []},
    ]
    monkeypatch.setattr(ex, "historico", SimpleNamespace(listar=lambda tid: registros))
    u = saude.ultimo_publish(tipo)
    assert u["url"] == "https://youtu.be/A"
    assert u["quando"] == "2026-07-05T10:05:00Z"


def test_ultimo_publish_none(monkeypatch, make_tipo):
    import operacoes.execucoes as ex

    tipo = make_tipo()
    monkeypatch.setattr(ex, "historico", SimpleNamespace(listar=lambda tid: [{"publicacao": []}]))
    assert saude.ultimo_publish(tipo) is None


# --- alerta periódico --------------------------------------------------------


def test_verificar_e_alertar_emite(monkeypatch):
    emitidas = []
    monkeypatch.setattr(
        notificacoes, "emitir",
        lambda cat, titulo, msg, prioridade=None: emitidas.append(cat) or True,
    )
    monkeypatch.setattr(saude, "disco", lambda: {"baixo": True, "caminho": "/x", "livre_gb": 1.0, "livre_pct": 3.0})
    monkeypatch.setattr(
        saude, "credenciais",
        lambda tipos=None: [{"status": "expirando", "tipo_nome": "T", "destino": "youtube", "detalhe": "d"}],
    )
    cats = saude.verificar_e_alertar()
    assert "disco_baixo" in cats
    assert "credencial" in cats


def test_verificar_e_alertar_silencioso_quando_ok(monkeypatch):
    emitidas = []
    monkeypatch.setattr(
        notificacoes, "emitir",
        lambda cat, titulo, msg, prioridade=None: emitidas.append(cat) or True,
    )
    monkeypatch.setattr(saude, "disco", lambda: {"baixo": False, "caminho": "/x", "livre_gb": 50.0, "livre_pct": 80.0})
    monkeypatch.setattr(saude, "credenciais", lambda tipos=None: [{"status": "valido", "tipo_nome": "T", "destino": "youtube", "detalhe": ""}])
    assert saude.verificar_e_alertar() == []
    assert emitidas == []
