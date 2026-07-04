from descoberta.fontes import reddit

_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Post Um</title></entry>
  <entry><title>Post Dois</title></entry>
  <entry><title></title></entry>
</feed>"""


def test_titulos_do_rss_parseia_e_ignora_vazios():
    assert reddit._titulos_do_rss(_RSS) == ["Post Um", "Post Dois"]


def test_buscar_um_sub(monkeypatch):
    monkeypatch.setattr(reddit, "_baixar", lambda url, timeout=30: _RSS)
    out = reddit.buscar(None, {"subreddits": ["brasil"], "limite": 20, "periodo": "day"})
    assert [c.texto for c in out] == ["Post Um", "Post Dois"]
    assert all(c.fonte == "reddit" for c in out)


def test_buscar_sub_que_falha_e_pulado(monkeypatch):
    def _falha(url, timeout=30):
        raise RuntimeError("403")

    monkeypatch.setattr(reddit, "_baixar", _falha)
    assert reddit.buscar(None, {"subreddits": ["x"], "limite": 5, "periodo": "day"}) == []


def test_buscar_sem_subs():
    assert reddit.buscar(None, {"subreddits": [], "limite": 5, "periodo": "day"}) == []
