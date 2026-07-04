from descoberta.fontes import google_trends as gt


def test_pais_mapeia_conhecidos_e_default():
    assert gt._pais("BR") == "brazil"
    assert gt._pais("us") == "united_states"
    assert gt._pais("ZZ") == "brazil"  # desconhecido cai no default


def test_buscar_usa_tendencias(monkeypatch):
    monkeypatch.setattr(gt, "_tendencias", lambda geo, limite: ["X", "Y"])
    out = gt.buscar(None, {"geo": "BR", "limite": 2})
    assert [c.texto for c in out] == ["X", "Y"]
    assert all(c.fonte == "google_trends" for c in out)


def test_buscar_repassa_geo_e_limite(monkeypatch):
    capturado = {}

    def _fake(geo, limite):
        capturado["geo"] = geo
        capturado["limite"] = limite
        return []

    monkeypatch.setattr(gt, "_tendencias", _fake)
    gt.buscar(None, {"geo": "PT", "limite": 7})
    assert capturado == {"geo": "PT", "limite": 7}
