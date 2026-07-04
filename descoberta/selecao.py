"""Seleção: transforma muitos candidatos em um só.

Combina força de sinal, fit e frescor numa pontuação ponderada (pesos
configuráveis em selecao.*) e pega o topo. Calculada fresca a cada run, não
persistida como ordem fixa. O frescor faz um sinal forte-porém-velho perder para
um mais novo — o que mantém o tema atual e envelhece o buffer no modo reter.
"""

from descoberta.candidato import Candidato, agora


def frescor(observado_em, agora_dt, meia_vida_horas: float) -> float:
    """Decaimento por meia-vida: 1.0 recém-observado, 0.5 após uma meia-vida."""
    idade_horas = (agora_dt - observado_em).total_seconds() / 3600.0
    if idade_horas <= 0:
        return 1.0
    return 0.5 ** (idade_horas / meia_vida_horas)


def pontuar(candidato: Candidato, cfg_selecao: dict, agora_dt) -> float:
    fit = (candidato.fit_score or 0.0) / 100.0
    fr = frescor(candidato.observado_em, agora_dt, cfg_selecao["meia_vida_horas"])
    return (
        cfg_selecao["peso_sinal"] * candidato.forca_sinal
        + cfg_selecao["peso_fit"] * fit
        + cfg_selecao["peso_frescor"] * fr
    )


def selecionar(candidatos: list, cfg_selecao: dict, agora_dt=None):
    """Devolve (candidato, pontuacao) do melhor candidato, ou (None, 0.0) se vazio."""
    if not candidatos:
        return None, 0.0
    agora_dt = agora_dt or agora()
    melhor = max(candidatos, key=lambda c: pontuar(c, cfg_selecao, agora_dt))
    return melhor, pontuar(melhor, cfg_selecao, agora_dt)
