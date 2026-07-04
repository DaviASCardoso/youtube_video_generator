"""Cliente do Gemini para avaliar o *fit* de um candidato a tema.

Recebe um candidato cru (ex.: "project hail mary") e o prompt de critério/persona
do tipo (system_prompt_tendencia.txt), e devolve uma avaliação estruturada: se
encaixa no canal (`aceito`), quão bem (`score` 0-100), o `tema` pronto para
roteiro e uma `justificativa`. O modelo pode dizer "não". Saída estruturada via
response_schema. Modelo: gemini-3.5-flash.

Precisa de GEMINI_API_KEY no .env. Usa o SDK google-genai (já instalado).
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

MODELO = "gemini-3.5-flash"


class AvaliacaoFit(BaseModel):
    """Formato estruturado que o Gemini deve devolver ao avaliar um candidato."""

    aceito: bool
    score: int
    tema: str
    justificativa: str


def avaliar_fit(candidato: str, system_prompt: str) -> AvaliacaoFit:
    """Avalia o quão bem um candidato a tema encaixa no canal.

    Args:
        candidato: O sinal/termo cru (nome vindo de uma fonte de tendência).
        system_prompt: Critério/persona do tipo (de system_prompt_tendencia.txt) —
            é ele que define o que é um "bom tema" para este canal.

    Returns:
        AvaliacaoFit com aceito, score (0-100), tema pronto e justificativa.

    Raises:
        RuntimeError: Se GEMINI_API_KEY não estiver configurada.
    """
    chave = os.getenv("GEMINI_API_KEY")
    if not chave:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")

    contents = (
        f'Candidato a tema, vindo de um sinal de tendência: "{candidato}".\n'
        "Avalie se ele rende um bom vídeo para ESTE canal. Devolva: aceito "
        "(true/false), score (0-100 de quão bem encaixa), tema (o tema pronto "
        "para virar roteiro, em pt-BR) e justificativa (curta). Se não tiver "
        "relação com o canal, use aceito=false e um score baixo."
    )

    cliente = genai.Client(api_key=chave)
    resposta = cliente.models.generate_content(
        model=MODELO,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=AvaliacaoFit,
        ),
    )

    resultado = resposta.parsed
    if not isinstance(resultado, AvaliacaoFit):
        # fallback defensivo: em raras respostas o SDK pode não popular .parsed
        resultado = AvaliacaoFit.model_validate_json(resposta.text)
    return resultado


if __name__ == "__main__":
    from config.tipos import carregar_tipo
    from descoberta.tendencias import _prompt_do_tipo

    tipo = carregar_tipo("cetico_pratico")
    avaliacao = avaliar_fit("project hail mary", _prompt_do_tipo(tipo))
    print("aceito:", avaliacao.aceito)
    print("score:", avaliacao.score)
    print("tema:", avaliacao.tema)
    print("justificativa:", avaliacao.justificativa)
