from descoberta.fontes import youtube as yt_fonte


class _FakeReq:
    def __init__(self, resp):
        self._resp = resp

    def execute(self):
        return self._resp


class _FakeSearch:
    def __init__(self, respostas):
        self._respostas = respostas
        self._i = 0

    def list(self, **kwargs):
        resp = self._respostas[self._i]
        self._i += 1
        return _FakeReq(resp)


class _FakeServico:
    def __init__(self, respostas):
        self._search = _FakeSearch(respostas)

    def search(self):
        return self._search


def test_titulos_extrai_snippets():
    resp = {"items": [{"snippet": {"title": "A"}}, {"snippet": {"title": ""}}, {"snippet": {}}]}
    assert yt_fonte._titulos(resp) == ["A"]


def test_buscar_consultas_e_canais(monkeypatch):
    respostas = [
        {"items": [{"snippet": {"title": "Busca1"}}]},
        {"items": [{"snippet": {"title": "Canal1"}}]},
    ]
    monkeypatch.setattr(yt_fonte._yt, "_servico", lambda tipo: _FakeServico(respostas))
    out = yt_fonte.buscar(
        None, {"limite": 5, "consultas": ["q"], "canais_nicho": ["c"], "regiao": "BR"}
    )
    assert {c.texto for c in out} == {"Busca1", "Canal1"}
    assert all(c.fonte == "youtube" for c in out)


def test_buscar_sem_token_degrada_via_coletar(monkeypatch):
    from descoberta.fontes import base

    def _sem_token(tipo):
        raise RuntimeError("sem credencial")

    monkeypatch.setattr(yt_fonte._yt, "_servico", _sem_token)
    # base.coletar tolera a exceção e devolve vazio
    assert base.coletar("youtube", None, {"consultas": ["q"]}) == []
