"""Fonte de sinal: Trends MCP (o feed de tendências original do projeto)."""

from descoberta import trends
from descoberta.fontes import base


@base.registrar("trends_mcp")
def buscar(tipo, cfg: dict) -> list:
    nomes = trends.buscar_tendencias(
        feed=cfg.get("feed", "Google Trends"),
        limite=int(cfg.get("limite", 25)),
    )
    return base.candidatos_por_rank(nomes, "trends_mcp")
