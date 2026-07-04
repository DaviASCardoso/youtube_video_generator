"""Fonte de sinal: Wikimedia Pageviews "top articles" de pt.wikipedia (sem chave).

Os artigos mais vistos do dia anterior são um proxy de atenção do público
lusófono. Sem chave, só precisa de um User-Agent. Só stdlib. Filtra páginas
meta (Especial:, Wikipédia:, a página principal, etc.).
"""

import json
import urllib.request
from datetime import timedelta

from descoberta.candidato import agora
from descoberta.fontes import base

USER_AGENT = "GeradorDeVideos/1.0 (descoberta de temas de canal; uso pessoal)"

_META_PREFIXOS = (
    "Especial:",
    "Wikipédia:",
    "Predefinição:",
    "Ajuda:",
    "Categoria:",
    "Portal:",
    "Ficheiro:",
    "Wikcionário:",
    "MediaWiki:",
    "Anexo:",
)
_META_EXATOS = {"Main_Page", "Página_principal", "Wikipédia", "Especial:Pesquisar"}


def _e_meta(artigo: str) -> bool:
    return (
        ":" in artigo
        or artigo in _META_EXATOS
        or artigo.startswith(_META_PREFIXOS)
    )


def _url_top(quando) -> str:
    return (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
        f"pt.wikipedia/all-access/{quando:%Y/%m/%d}"
    )


def _baixar(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _artigos(payload_json: str, limite: int) -> list[str]:
    dados = json.loads(payload_json)
    itens = dados["items"][0]["articles"]  # já em ordem de views (rank)
    nomes = []
    for item in itens:
        artigo = (item.get("article") or "").strip()
        if not artigo or _e_meta(artigo):
            continue
        nomes.append(artigo.replace("_", " "))
        if len(nomes) >= limite:
            break
    return nomes


@base.registrar("wikipedia")
def buscar(tipo, cfg: dict) -> list:
    limite = int(cfg.get("limite", 20))
    # Dia anterior: o "top" de hoje pode ainda não estar disponível.
    quando = agora() - timedelta(days=1)
    payload = _baixar(_url_top(quando))
    return base.candidatos_por_rank(_artigos(payload, limite), "wikipedia")
