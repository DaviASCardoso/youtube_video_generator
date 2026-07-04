import json

import pytest

from geracao import pexels
from geracao.pexels import buscar_imagem, tem_chave


class _RespostaFake:
    def __init__(self, corpo: bytes):
        self._corpo = corpo

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_tem_chave(monkeypatch):
    assert tem_chave() is False  # limpar_env removeu a chave
    monkeypatch.setenv("PEXELS_API_KEY", "abc")
    assert tem_chave() is True


def test_buscar_sem_chave_retorna_none():
    assert buscar_imagem("office") is None


def test_buscar_retorna_bytes_e_manda_user_agent(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "abc")
    reqs = []

    busca = json.dumps(
        {"photos": [{"src": {"large2x": "http://img/2x.jpg", "original": "http://img/o.jpg"}}]}
    ).encode()

    def fake_urlopen(req, timeout=60):
        reqs.append(req)
        if req.full_url.startswith("https://api.pexels.com"):
            return _RespostaFake(busca)
        return _RespostaFake(b"bytes-da-foto")

    monkeypatch.setattr(pexels.urllib.request, "urlopen", fake_urlopen)

    dados = buscar_imagem("office desk")
    assert dados == b"bytes-da-foto"
    # o header de navegador é obrigatório (senão o Pexels responde 403)
    assert all("Mozilla" in r.headers["User-agent"] for r in reqs)
    # a segunda requisição baixa a URL large2x
    assert reqs[1].full_url == "http://img/2x.jpg"


def test_buscar_sem_resultados_retorna_none(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "abc")
    monkeypatch.setattr(
        pexels.urllib.request,
        "urlopen",
        lambda req, timeout=60: _RespostaFake(json.dumps({"photos": []}).encode()),
    )
    assert buscar_imagem("nada") is None


def test_buscar_erro_de_rede_retorna_none(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "abc")

    def falha(req, timeout=60):
        raise OSError("sem rede")

    monkeypatch.setattr(pexels.urllib.request, "urlopen", falha)
    assert buscar_imagem("office") is None
