"""Deduplicação: não propor o que o canal efetivamente já fez.

Compara um candidato (normalizado) com um conjunto de textos já vistos —
sinais recentemente consumidos e temas já decididos/produzidos — de forma
robusta a reescritas triviais, não só a nome idêntico. A janela e a estratégia/
rigidez do casamento são configuráveis (dedup.dias / dedup.estrategia /
dedup.limiar).

`sinais_recentes` lê o `HistoricoTendencias` (sinais consumidos). O orquestrador
une esse conjunto com os temas já decididos (do estado da Descoberta) antes de
filtrar — assim este módulo não importa Operações.
"""

from descoberta.tendencias import _normalizar, historico_tendencias


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def repetido(texto: str, ja_vistos: set[str], estrategia: str, limiar: float) -> bool:
    """Diz se `texto` já aparece (dado o conjunto de vistos, normalizados).

    Args:
        texto: Texto cru do candidato.
        ja_vistos: Textos já vistos, JÁ normalizados (ver `_normalizar`).
        estrategia: "exato" (nome normalizado idêntico) ou "token" (sobreposição
            de tokens Jaccard ≥ limiar, pega reescritas).
        limiar: Limiar de Jaccard (0..1), usado só na estratégia "token".
    """
    alvo = _normalizar(texto)
    if not alvo:
        return False
    if estrategia == "exato":
        return alvo in ja_vistos

    tokens_alvo = set(alvo.split())
    for visto in ja_vistos:
        if _jaccard(tokens_alvo, set(visto.split())) >= limiar:
            return True
    return False


def sinais_recentes(tipo, dias: int) -> set[str]:
    """Conjunto de sinais (normalizados) consumidos por um tipo nos últimos `dias`."""
    return historico_tendencias.trends_recentes(tipo.id, dias)


def filtrar(candidatos: list, ja_vistos: set[str], cfg_descoberta: dict) -> list:
    """Remove da lista os candidatos considerados repetidos."""
    estrategia = cfg_descoberta["dedup"]["estrategia"]
    limiar = cfg_descoberta["dedup"]["limiar"]
    return [
        c for c in candidatos if not repetido(c.texto, ja_vistos, estrategia, limiar)
    ]
