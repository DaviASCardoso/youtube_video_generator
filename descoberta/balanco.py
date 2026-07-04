"""Balanço trending/evergreen — decidido por ciclo, não guardado como fila.

Olha o histórico recente de categorias produzidas por um tipo e decide se o tema
deste ciclo deve ser trending ou evergreen, para manter a fração-alvo evergreen
(`evergreen_ratio`) ao longo do tempo. O orquestrador então prioriza os
candidatos da categoria escolhida.
"""


def categoria_do_ciclo(historico_categorias: list[str], evergreen_ratio: float) -> str:
    """Escolhe "trending" ou "evergreen" para este ciclo.

    Args:
        historico_categorias: Categorias dos últimos temas produzidos (mais
            recente em qualquer ordem — só a proporção importa).
        evergreen_ratio: Fração-alvo de ciclos evergreen (0..1).

    Returns:
        "trending" ou "evergreen".
    """
    if evergreen_ratio <= 0:
        return "trending"
    if evergreen_ratio >= 1:
        return "evergreen"

    total = len(historico_categorias)
    if total == 0:
        # Sem histórico: começa conforme o alvo pende para um lado.
        return "evergreen" if evergreen_ratio >= 0.5 else "trending"

    fracao_evergreen = sum(1 for c in historico_categorias if c == "evergreen") / total
    return "evergreen" if fracao_evergreen < evergreen_ratio else "trending"
