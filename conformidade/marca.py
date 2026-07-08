"""Checagem 4 — brand safety / apropriação do tema.

Como a Descoberta puxa temas de tendências, o sistema poderia fazer um vídeo sobre algo
ofensivo, trágico ou sensível só porque estava em alta. Esta checagem veta temas
inapropriados **na borda da Descoberta**, antes de a produção gastar qualquer coisa.

Duas camadas: uma **objetiva** (listas versionadas de termos de bloqueio e sensíveis) e
uma **de julgamento** (Groq avalia o caso limítrofe que não bate numa lista). O caso
inequívoco (lista de bloqueio) é clear-cut → bloqueia; o limítrofe (lista sensível ou o
Groq) → sinaliza para o humano. O `modo` efetivo modula: `bloquear` endurece tudo para
bloqueio, `advisory` afrouxa tudo para flag, `equilibrada` (padrão) bloqueia o inequívoco
e sinaliza o limítrofe.

O Groq **falha aberto**: sem chave ou em erro, a camada de julgamento não sinaliza nada —
a camada objetiva (o bloqueio de verdade) nunca depende do LLM.
"""

import json
import re

from geracao.generate_script import _chamar_api
from conformidade.parecer import BLOQUEADO, FLAG, LIBERADO, Veredito

_SYSTEM_PROMPT = (
    "Você é um revisor de brand safety para um canal do YouTube. Dado um TEMA de vídeo, "
    "decida se ele é apropriado para um canal generalista de desenvolvimento pessoal — "
    "evitando conteúdo ofensivo, trágico, sensível, sexual, violento ou que atraia "
    "restrição de anúncios. Responda SOMENTE um JSON: "
    '{"apropriado": true|false, "motivo": "curto"}'
)


def _parsear(resposta: str) -> dict:
    resposta = re.sub(r"```(?:json)?\s*", "", resposta).strip().rstrip("`").strip()
    dados = json.loads(resposta)
    return dados if isinstance(dados, dict) else {}


def _bate_lista(tema: str, termos) -> str | None:
    """Primeiro termo da lista contido no tema (case-insensitive), ou None."""
    baixo = tema.lower()
    for termo in termos or []:
        if termo and termo.lower() in baixo:
            return termo
    return None


def _groq_limitrofe(tema: str, config) -> tuple[bool, str]:
    """Camada de julgamento (Groq). Devolve (limitrofe, motivo). Falha aberto:
    qualquer erro/ausência de chave ⇒ (False, "")."""
    try:
        bruto = _parsear(_chamar_api(_SYSTEM_PROMPT, f"TEMA: {tema}", config))
    except Exception:  # noqa: BLE001 (fail-open: o LLM nunca bloqueia sozinho)
        return False, ""
    if bruto.get("apropriado") is False:
        return True, str(bruto.get("motivo", "")).strip()
    return False, ""


def avaliar_tema(tema: str, modo: str, regras: dict, config) -> Veredito:
    """Avalia um tema quanto a brand safety.

    Args:
        tema: o tema decidido pela Descoberta.
        modo: o modo efetivo desta checagem (`advisory`/`equilibrada`/`bloquear`).
        regras: o conteúdo de regras vigente (usa `regras["marca"]`).
        config: a config do tipo (para a chamada Groq da camada de julgamento).

    Returns:
        Um `Veredito` (`liberado`/`bloqueado`/`flag`).
    """
    marca = regras.get("marca", {})

    # Camada objetiva: bloqueio (clear-cut) tem prioridade e dispensa o Groq.
    termo_bloqueio = _bate_lista(tema, marca.get("bloqueio", []))
    if termo_bloqueio:
        if modo == "advisory":
            return Veredito(FLAG, f"termo de bloqueio '{termo_bloqueio}' (advisory)")
        return Veredito(BLOQUEADO, f"termo de bloqueio: '{termo_bloqueio}'")

    # Limítrofe: lista sensível OU julgamento do Groq.
    termo_sensivel = _bate_lista(tema, marca.get("sensivel", []))
    limitrofe_groq, motivo_groq = _groq_limitrofe(tema, config)

    if termo_sensivel or limitrofe_groq:
        motivo = (
            f"termo sensível: '{termo_sensivel}'" if termo_sensivel
            else f"julgamento: {motivo_groq or 'tema limítrofe'}"
        )
        if modo == "bloquear":
            return Veredito(BLOQUEADO, motivo)
        return Veredito(FLAG, motivo)

    return Veredito(LIBERADO)
