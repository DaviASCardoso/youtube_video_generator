"""Fonte de sinal: feeds públicos .rss do Reddit (sem chave).

Lê /r/<sub>/top/.rss?t=<periodo> de cada subreddit configurado. Precisa de um
User-Agent descritivo (senão o Reddit responde 403) e vai gentil (uma pequena
pausa entre subs). Só stdlib (urllib + xml). Feed não-oficial → degrada por sub.
"""

import time
import urllib.request
import xml.etree.ElementTree as ET

from descoberta.fontes import base

USER_AGENT = "GeradorDeVideos/1.0 (descoberta de temas de canal; uso pessoal)"
_ATOM = "{http://www.w3.org/2005/Atom}"


def _baixar(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _titulos_do_rss(xml_texto: str) -> list[str]:
    raiz = ET.fromstring(xml_texto)
    titulos = []
    for entrada in raiz.findall(f"{_ATOM}entry"):
        titulo = (entrada.findtext(f"{_ATOM}title") or "").strip()
        if titulo:
            titulos.append(titulo)
    return titulos


@base.registrar("reddit")
def buscar(tipo, cfg: dict) -> list:
    subs = cfg.get("subreddits") or []
    limite = int(cfg.get("limite", 20))
    periodo = cfg.get("periodo", "day")

    titulos: list[str] = []
    for i, sub in enumerate(subs):
        if i:
            time.sleep(1)  # rate gentil entre subreddits
        url = f"https://www.reddit.com/r/{sub}/top/.rss?t={periodo}&limit={limite}"
        try:
            xml_texto = _baixar(url)
        except Exception as e:
            print(f"    [descoberta:reddit] falha em r/{sub}: {e}")
            continue
        titulos.extend(_titulos_do_rss(xml_texto)[:limite])

    return base.candidatos_por_rank(titulos, "reddit")
