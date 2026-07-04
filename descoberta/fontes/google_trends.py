"""Fonte de sinal: Google Trends via o fork mantido `pytrends-modern`.

O `pytrends` original foi arquivado em abril/2025; usamos o fork `pytrends-modern`
(import `pytrends_modern.request`). Por ser não-oficial e frágil, o import é
preguiçoso (dependência opcional) e qualquer falha degrada para nada.
"""

from descoberta.fontes import base

# Mapeia o código de país (geo) para o nome que trending_searches espera (pn).
_PAISES = {
    "BR": "brazil",
    "US": "united_states",
    "PT": "portugal",
    "GB": "united_kingdom",
    "ES": "spain",
    "FR": "france",
    "DE": "germany",
}


def _pais(geo: str) -> str:
    return _PAISES.get(geo.upper(), "brazil")


def _tendencias(geo: str, limite: int) -> list[str]:
    # Import tardio: dependência opcional/frágil (fork pytrends-modern).
    from pytrends_modern.request import TrendReq

    cliente = TrendReq(hl="pt-BR", tz=180)
    df = cliente.trending_searches(pn=_pais(geo))
    termos = [str(x).strip() for x in df.iloc[:, 0].tolist()]
    return termos[:limite]


@base.registrar("google_trends")
def buscar(tipo, cfg: dict) -> list:
    termos = _tendencias(cfg.get("geo", "BR"), int(cfg.get("limite", 20)))
    return base.candidatos_por_rank(termos, "google_trends")
