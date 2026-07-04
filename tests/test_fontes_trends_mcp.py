from descoberta.fontes import trends_mcp


def test_buscar_mapeia_tendencias(monkeypatch):
    monkeypatch.setattr(
        trends_mcp.trends, "buscar_tendencias", lambda feed, limite: ["T1", "T2", "T3"]
    )
    out = trends_mcp.buscar(None, {"feed": "Google Trends", "limite": 3})
    assert [c.texto for c in out] == ["T1", "T2", "T3"]
    assert all(c.fonte == "trends_mcp" and c.categoria == "trending" for c in out)


def test_buscar_sem_tendencias(monkeypatch):
    monkeypatch.setattr(trends_mcp.trends, "buscar_tendencias", lambda feed, limite: [])
    assert trends_mcp.buscar(None, {}) == []
