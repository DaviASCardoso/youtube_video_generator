"""Checagem 5 — precisão factual (opcional, advisory, desligada por padrão).

A persona é um pragmático cético, então publicar uma alegação falsa fere a marca e
flerta com a política de desinformação. Esta camada, com Groq, checa se um vídeo afirma
algo **verificável e errado**. É a checagem mais difícil de automatizar bem, então existe
como um **interruptor** (desligada por padrão); ligada, é **advisory** — nunca um gate
sempre-ligado inflado. O `ativo` é decidido pelo orquestrador; aqui só roda a checagem.

O Groq **falha aberto**: erro/sem chave ⇒ sem sinal.
"""

import json
import re

from geracao.generate_script import _chamar_api

_SYSTEM_PROMPT = (
    "Você é um verificador de fatos. Dado o ROTEIRO de um vídeo, identifique apenas as "
    "alegações que são VERIFICÁVEIS e FALSAS (não opiniões, não conselhos, não generalizações). "
    "Seja conservador: só liste o que é claramente incorreto. "
    'Responda SOMENTE um JSON: {"alegacoes_falsas": ["curto", ...]}'
)


def _parsear(resposta: str) -> dict:
    resposta = re.sub(r"```(?:json)?\s*", "", resposta).strip().rstrip("`").strip()
    dados = json.loads(resposta)
    return dados if isinstance(dados, dict) else {}


def verificar_factual(roteiro: str, config) -> dict:
    """Checa o roteiro por alegações verificáveis e falsas.

    Returns:
        `{"flag": bool, "alegacoes": [str]}`. Falha aberto ⇒ `{"flag": False, ...}`.
    """
    try:
        bruto = _parsear(_chamar_api(_SYSTEM_PROMPT, f"ROTEIRO:\n{roteiro}", config))
    except Exception:  # noqa: BLE001 (fail-open)
        return {"flag": False, "alegacoes": []}
    alegacoes = [str(a).strip() for a in (bruto.get("alegacoes_falsas") or []) if str(a).strip()]
    return {"flag": bool(alegacoes), "alegacoes": alegacoes}
