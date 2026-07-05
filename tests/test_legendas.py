from geracao import legendas
from geracao.legendas import _timestamp, montar_srt


def test_timestamp_formata_srt():
    assert _timestamp(0) == "00:00:00,000"
    assert _timestamp(1.5) == "00:00:01,500"
    assert _timestamp(3661.25) == "01:01:01,250"


def test_montar_srt_acumula_tempos():
    srt = montar_srt([("primeira", 2.0), ("segunda", 1.5)])
    assert "1\n00:00:00,000 --> 00:00:02,000\nprimeira" in srt
    assert "2\n00:00:02,000 --> 00:00:03,500\nsegunda" in srt


def test_escrever_srt(tmp_path):
    caminho = legendas.escrever_srt(tmp_path / "l.srt", [("oi", 1.0)])
    assert caminho.exists()
    assert "oi" in caminho.read_text(encoding="utf-8")


# --- burn-in (moviepy monkeypatchado) ------------------------------------


class _FakeClipe:
    duration = 2.0


class _FakeTextClip:
    def __init__(self, **k):
        self.kwargs = k

    def with_duration(self, d):
        return self

    def with_position(self, p):
        self.pos = p
        return self


def test_sobrepor_sem_moviepy_devolve_original(monkeypatch):
    monkeypatch.setattr(legendas, "TextClip", None)
    monkeypatch.setattr(legendas, "CompositeVideoClip", None)
    clipes = [_FakeClipe()]
    assert legendas.sobrepor_legendas(clipes, [("t", 1.0)], {}) is clipes


def test_sobrepor_compoe_por_cena(monkeypatch):
    monkeypatch.setattr(legendas, "TextClip", _FakeTextClip)
    monkeypatch.setattr(legendas, "CompositeVideoClip", lambda camadas: ("composto", camadas))
    clipes = [_FakeClipe(), _FakeClipe()]
    out = legendas.sobrepor_legendas(
        clipes, [("a", 1.0), ("b", 1.0)], {"posicao": "superior", "tamanho": 40, "cor": "#000000"}
    )
    assert len(out) == 2
    assert all(c[0] == "composto" for c in out)


def test_sobrepor_degrada_em_falha(monkeypatch):
    def _explode(**k):
        raise RuntimeError("sem fonte")

    monkeypatch.setattr(legendas, "TextClip", _explode)
    monkeypatch.setattr(legendas, "CompositeVideoClip", lambda camadas: ("composto", camadas))
    clipe = _FakeClipe()
    out = legendas.sobrepor_legendas([clipe], [("a", 1.0)], {})
    assert out == [clipe]  # caiu para o clipe original
