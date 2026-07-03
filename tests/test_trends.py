import json

import pytest

from scripts import trends
from scripts.trends import buscar_tendencias, tem_chave


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
    assert tem_chave() is False
    monkeypatch.setenv("TRENDS_MCP_API_KEY", "abc")
    assert tem_chave() is True


def test_sem_chave_retorna_lista_vazia():
    assert buscar_tendencias() == []


def test_desembrulha_body_e_extrai_nomes(monkeypatch):
    monkeypatch.setenv("TRENDS_MCP_API_KEY", "abc")
    # a API embrulha o payload: body é uma STRING JSON com data=[[rank, nome]]
    corpo_interno = json.dumps({"data": [[1, "Trend Um"], [2, "Trend Dois"]]})
    externo = json.dumps({"statusCode": 200, "body": corpo_interno}).encode()

    monkeypatch.setattr(
        trends.urllib.request,
        "urlopen",
        lambda req, timeout=60: _RespostaFake(externo),
    )
    assert buscar_tendencias() == ["Trend Um", "Trend Dois"]


def test_body_dict_tambem_funciona(monkeypatch):
    monkeypatch.setenv("TRENDS_MCP_API_KEY", "abc")
    externo = json.dumps(
        {"statusCode": 200, "body": {"data": [[1, "X"]]}}
    ).encode()
    monkeypatch.setattr(
        trends.urllib.request,
        "urlopen",
        lambda req, timeout=60: _RespostaFake(externo),
    )
    assert buscar_tendencias() == ["X"]


def test_erro_de_rede_retorna_vazio(monkeypatch):
    monkeypatch.setenv("TRENDS_MCP_API_KEY", "abc")

    def falha(req, timeout=60):
        raise OSError("sem rede")

    monkeypatch.setattr(trends.urllib.request, "urlopen", falha)
    assert buscar_tendencias() == []


def test_body_invalido_retorna_vazio(monkeypatch):
    monkeypatch.setenv("TRENDS_MCP_API_KEY", "abc")
    externo = json.dumps({"statusCode": 200, "body": "{ nao e json"}).encode()
    monkeypatch.setattr(
        trends.urllib.request,
        "urlopen",
        lambda req, timeout=60: _RespostaFake(externo),
    )
    assert buscar_tendencias() == []
