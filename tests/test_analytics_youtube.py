import pytest

from feedback import analytics_youtube as ay
from feedback.destinos import base as destinos


# --- fakes do serviço Google (nenhuma chamada real) -------------------------


class _FakeQuery:
    def __init__(self, resp):
        self._resp = resp

    def execute(self):
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


class _FakeReports:
    def __init__(self, metricas_resp, curva_resp, falha_se_ctr=False):
        self.metricas_resp = metricas_resp
        self.curva_resp = curva_resp
        self.falha_se_ctr = falha_se_ctr
        self.consultas = []

    def query(self, **kw):
        self.consultas.append(kw)
        if "dimensions" in kw:
            return _FakeQuery(self.curva_resp)
        if self.falha_se_ctr and "cardClickRate" in kw.get("metrics", ""):
            return _FakeQuery(RuntimeError("cardClickRate indisponível"))
        return _FakeQuery(self.metricas_resp)


class _FakeServico:
    def __init__(self, reports):
        self._reports = reports

    def reports(self):
        return self._reports


def _mock(monkeypatch, reports, canal="CID"):
    monkeypatch.setattr(ay, "_servico_analytics", lambda tipo: _FakeServico(reports))
    monkeypatch.setattr(ay, "_canal_id", lambda tipo: canal)


# --- coletar ----------------------------------------------------------------


def test_coleta_metricas_e_curva(monkeypatch):
    reports = _FakeReports(
        metricas_resp={"rows": [[52.0, 1000, 300, 12, 0.05]]},
        curva_resp={"rows": [[0.0, 1.0], [0.5, 0.7], [1.0, 0.4]]},
    )
    _mock(monkeypatch, reports)

    out = ay.coletar(object(), "vid1", "2026-07-01")
    assert out["avg_view_pct"] == 52.0
    assert out["views"] == 1000
    assert out["watch_time"] == 300
    assert out["subs"] == 12
    assert out["ctr"] == 0.05
    assert out["curva"] == [[0.0, 1.0], [0.5, 0.7], [1.0, 0.4]]
    assert out["coletado_em"]


def test_filtro_por_video_e_janela(monkeypatch):
    reports = _FakeReports({"rows": [[10, 20, 30, 1, 0.1]]}, {"rows": []})
    _mock(monkeypatch, reports)
    ay.coletar(object(), "abc", "2026-06-01")
    consulta_metricas = reports.consultas[0]
    assert consulta_metricas["filters"] == "video==abc"
    assert consulta_metricas["startDate"] == "2026-06-01"
    assert consulta_metricas["ids"] == "channel==CID"


def test_sem_credencial_devolve_none(monkeypatch):
    monkeypatch.setattr(ay, "_servico_analytics", lambda tipo: (_ for _ in ()).throw(RuntimeError("sem token")))
    assert ay.coletar(object(), "v", "2026-07-01") is None


def test_canal_indisponivel_devolve_none(monkeypatch):
    reports = _FakeReports({"rows": []}, {"rows": []})
    monkeypatch.setattr(ay, "_servico_analytics", lambda tipo: _FakeServico(reports))
    monkeypatch.setattr(ay, "_canal_id", lambda tipo: (_ for _ in ()).throw(RuntimeError("sem canal")))
    assert ay.coletar(object(), "v", "2026-07-01") is None


def test_sem_dados_devolve_none(monkeypatch):
    reports = _FakeReports({"rows": []}, {"rows": []})
    _mock(monkeypatch, reports)
    assert ay.coletar(object(), "v", "2026-07-01") is None


def test_fallback_para_nucleo_quando_ctr_falha(monkeypatch):
    # a consulta cheia (com cardClickRate) falha; o retry sem ctr sucede
    reports = _FakeReports(
        metricas_resp={"rows": [[52.0, 1000, 300, 12]]},  # 4 métricas do núcleo
        curva_resp={"rows": []},
        falha_se_ctr=True,
    )
    _mock(monkeypatch, reports)
    out = ay.coletar(object(), "v", "2026-07-01")
    assert out["avg_view_pct"] == 52.0
    assert out["views"] == 1000
    assert "ctr" not in out  # a métrica indisponível foi deixada de fora
    # duas consultas de métricas (cheia falhou, núcleo passou) + a da curva
    metricas = [c for c in reports.consultas if "dimensions" not in c]
    assert len(metricas) == 2


def test_curva_falha_nao_derruba_metricas(monkeypatch):
    reports = _FakeReports(
        metricas_resp={"rows": [[52.0, 1000, 300, 12, 0.05]]},
        curva_resp=RuntimeError("curva falhou"),
    )
    _mock(monkeypatch, reports)
    out = ay.coletar(object(), "v", "2026-07-01")
    assert out["avg_view_pct"] == 52.0
    assert out["curva"] == []


def test_chaves_customizadas(monkeypatch):
    reports = _FakeReports({"rows": [[52.0, 1000]]}, {"rows": []})
    _mock(monkeypatch, reports)
    out = ay.coletar(object(), "v", "2026-07-01", chaves=["avg_view_pct", "views"])
    assert set(out) >= {"avg_view_pct", "views"}
    assert "subs" not in out


# --- checar -----------------------------------------------------------------


def test_checar_valido(monkeypatch):
    monkeypatch.setattr(ay, "_canal_id", lambda tipo: "CID")
    assert ay.checar(object()) == {"status": "valido", "detalhe": "CID"}


def test_checar_erro(monkeypatch):
    monkeypatch.setattr(ay, "_canal_id", lambda tipo: (_ for _ in ()).throw(RuntimeError("nope")))
    r = ay.checar(object())
    assert r["status"] == "erro"
    assert "nope" in r["detalhe"]


# --- destino ----------------------------------------------------------------


def test_destino_registrado():
    assert destinos.disponiveis() == ["youtube"]
    d = destinos.obter("youtube")
    assert d.nome == "youtube"


def test_destino_delega_para_coletar(monkeypatch):
    d = destinos.obter("youtube")
    monkeypatch.setattr(ay, "coletar", lambda tipo, vid, pub, chaves=None: {"marcador": vid})
    assert d.metricas_do_video(object(), "xyz", "2026-07-01") == {"marcador": "xyz"}


def test_destino_desconhecido_levanta():
    with pytest.raises(KeyError):
        destinos.obter("tiktok")
