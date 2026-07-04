"""Fontes input-side: pool de ideias manuais e evergreen (do temas.json do tipo).

Diferente das fontes de tendência (que decaem), ideias curadas são baratas e
persistentes. O pool vive no temas.json do tipo (FilaDeTemas); cada ideia carrega
um `fonte` que a classifica: "manual" (ideias específicas curadas → categoria
trending) ou "evergreen" (temas atemporais → categoria evergreen). A ordem no
pool (prioridade) vira a força de sinal por rank.
"""

from descoberta.fontes import base


def _do_pool(tipo, fonte_pool: str, categoria: str) -> list:
    registros = [r for r in tipo.temas.listar() if r.get("fonte") == fonte_pool]
    textos = [r.get("tema", "") for r in registros]
    return base.candidatos_por_rank(textos, fonte_pool, categoria=categoria)


@base.registrar("manual")
def buscar_manual(tipo, cfg: dict) -> list:
    return _do_pool(tipo, "manual", "trending")


@base.registrar("evergreen")
def buscar_evergreen(tipo, cfg: dict) -> list:
    return _do_pool(tipo, "evergreen", "evergreen")
