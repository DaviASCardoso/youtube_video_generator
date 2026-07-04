"""Avaliação de fit por tipo — o passo caro (LLM) da Descoberta.

Trending não é o mesmo que valer-a-pena-fazer para ESTE canal. `avaliar` chama o
Gemini com o critério/persona do tipo (system_prompt_tendencia.txt), preenche
`fit_score`/`tema`/`justificativa` no candidato e diz se passou no score mínimo
configurado. Pela eficiência, o orquestrador só chama isto nos top contenders —
nunca no lote inteiro — e nunca reavalia um candidato que já tem `fit_score`.
"""

from descoberta import gemini
from descoberta.candidato import Candidato
from descoberta.tendencias import _prompt_do_tipo


def avaliar(candidato: Candidato, tipo, cfg_descoberta: dict) -> bool:
    """Avalia o fit de um candidato (chama o LLM) e o preenche in-place.

    Args:
        candidato: O candidato a avaliar (ainda sem fit_score).
        tipo: O tipo de vídeo (dá o prompt de critério/persona).
        cfg_descoberta: Bloco `descoberta` já mesclado (usa fit.score_minimo).

    Returns:
        True se o modelo aceitou E o score bateu o mínimo; False caso contrário.
    """
    avaliacao = gemini.avaliar_fit(candidato.texto, _prompt_do_tipo(tipo))
    candidato.fit_score = float(avaliacao.score)
    candidato.justificativa = avaliacao.justificativa
    candidato.tema = avaliacao.tema

    minimo = cfg_descoberta["fit"]["score_minimo"]
    return avaliacao.aceito and avaliacao.score >= minimo
