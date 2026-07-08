"""Checagem 2 — autenticidade / anti-slop (advisory, duas camadas).

A mais crítica: a plataforma renomeou a política para *inauthentic content* (jul/2025) e
a aplica contra canais mass-produced. Duas camadas:

- **Objetiva** — verifica que os sinais de proteção existem: a variação da Geração está
  ativa e suficiente, e a persona/ponto de vista do canal está no lugar.
- **Ambiciosa** — usa Groq para comparar o novo roteiro com os recentes e estimar o quão
  template-idêntica a saída está ficando (o padrão "a mesma coisa todo dia" que o algoritmo
  mira), sinalizando quando o sameness sobe.

Ambas são **advisory**: sinalizam um aviso no gate de revisão em vez de bloquear — um
julgamento de máquina de "isto parece slop" às vezes erra, e um veto automático faria
desligarem o pilar. O Groq **falha aberto** (erro/sem chave ⇒ sameness não computado, sem
sinal dessa camada).
"""

import json
import re

from geracao.generate_script import _chamar_api

# Comprimento mínimo do prompt de persona para contar como "persona/POV presente".
_MIN_PERSONA_CHARS = 20

_SYSTEM_PROMPT = (
    "Você audita a autenticidade de um canal do YouTube. Dado o ROTEIRO NOVO e uma lista de "
    "ROTEIROS RECENTES do mesmo canal, estime o quão template-idêntica / repetitiva a saída "
    "está ficando — o padrão 'a mesma coisa todo dia' que a política de conteúdo inautêntico "
    "penaliza. Dê um sameness de 0 (cada vídeo é único) a 100 (praticamente o mesmo vídeo). "
    'Responda SOMENTE um JSON: {"sameness": 0-100, "motivo": "curto"}'
)


def _parsear(resposta: str) -> dict:
    resposta = re.sub(r"```(?:json)?\s*", "", resposta).strip().rstrip("`").strip()
    dados = json.loads(resposta)
    return dados if isinstance(dados, dict) else {}


def _sameness_groq(roteiro_novo: str, roteiros_recentes: list[str], config) -> tuple[int | None, str]:
    """Camada ambiciosa (Groq). Devolve (sameness|None, motivo). Falha aberto."""
    if not roteiros_recentes:
        return None, "sem vídeos recentes para comparar"
    recentes = "\n\n---\n\n".join(roteiros_recentes)
    user = f"ROTEIRO NOVO:\n{roteiro_novo}\n\n===\n\nROTEIROS RECENTES:\n{recentes}"
    try:
        bruto = _parsear(_chamar_api(_SYSTEM_PROMPT, user, config))
    except Exception:  # noqa: BLE001 (fail-open)
        return None, ""
    try:
        sameness = int(round(float(bruto.get("sameness"))))
    except (TypeError, ValueError):
        return None, ""
    return max(0, min(100, sameness)), str(bruto.get("motivo", "")).strip()


def verificar_autenticidade(
    roteiro_novo: str,
    roteiros_recentes: list[str],
    variacao_cfg: float,
    persona_texto: str,
    cfg_check: dict,
    config,
) -> dict:
    """Roda as duas camadas de autenticidade.

    Args:
        roteiro_novo: o roteiro do vídeo sendo avaliado.
        roteiros_recentes: roteiros dos vídeos recentes do mesmo tipo.
        variacao_cfg: o valor de `geracao.variacao` do tipo (força da variação).
        persona_texto: o system prompt de roteiro do tipo (persona/POV).
        cfg_check: `checagens.autenticidade` (`variacao_minima`, `teto_sameness`, `n_recentes`).
        config: a config do tipo (para a chamada Groq).

    Returns:
        `{"flag": bool, "motivos": [str], "variacao_ok": bool, "persona_ok": bool,
          "sameness": int|None}`.
    """
    motivos: list[str] = []

    variacao_ok = float(variacao_cfg or 0.0) >= float(cfg_check.get("variacao_minima", 0.25))
    if not variacao_ok:
        motivos.append(f"variação insuficiente ({variacao_cfg} < {cfg_check.get('variacao_minima')})")

    persona_ok = bool(persona_texto and len(persona_texto.strip()) >= _MIN_PERSONA_CHARS)
    if not persona_ok:
        motivos.append("persona/ponto de vista ausente ou fraca")

    recentes = list(roteiros_recentes or [])[: int(cfg_check.get("n_recentes", 5))]
    sameness, motivo_sameness = _sameness_groq(roteiro_novo, recentes, config)
    if sameness is not None and sameness > int(cfg_check.get("teto_sameness", 70)):
        motivos.append(f"sameness alto ({sameness}) — {motivo_sameness or 'saída repetitiva'}")

    return {
        "flag": bool(motivos),
        "motivos": motivos,
        "variacao_ok": variacao_ok,
        "persona_ok": persona_ok,
        "sameness": sameness,
    }
