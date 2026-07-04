"""Cliente do Gemini para transformar uma tendência num tema do canal.

Recebe uma tendência crua (ex.: "project hail mary") e o prompt de instruções do
tipo (system_prompt_tendencia.txt), e devolve um tema pronto para a fila, com
saída estruturada (JSON) via response_schema. Modelo: gemini-3.5-flash.

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


class TemaTendencia(BaseModel):
    """Formato estruturado que o Gemini deve devolver."""

    tema: str
    justificativa: str


def gerar_tema_de_tendencia(tendencia: str, system_prompt: str) -> TemaTendencia:
    """Gera um tema de vídeo a partir de uma tendência, no contexto do canal.

    Args:
        tendencia: O termo em alta (nome cru vindo do Trends MCP).
        system_prompt: Instruções do tipo (persona/estilo + como converter a
            tendência em tema). Vem de system_prompt_tendencia.txt.

    Returns:
        TemaTendencia com o tema pronto para a fila e uma breve justificativa.

    Raises:
        RuntimeError: Se GEMINI_API_KEY não estiver configurada.
    """
    chave = os.getenv("GEMINI_API_KEY")
    if not chave:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")

    cliente = genai.Client(api_key=chave)
    resposta = cliente.models.generate_content(
        model=MODELO,
        contents=f"Tendência em alta hoje: {tendencia}",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=TemaTendencia,
        ),
    )

    resultado = resposta.parsed
    if not isinstance(resultado, TemaTendencia):
        # fallback defensivo: em raras respostas o SDK pode não popular .parsed
        resultado = TemaTendencia.model_validate_json(resposta.text)
    return resultado


if __name__ == "__main__":
    from config.tipos import carregar_tipo

    tipo = carregar_tipo("cetico_pratico")
    caminho = tipo.assets_dir / "system_prompt_tendencia.txt"
    prompt = caminho.read_text(encoding="utf-8").strip() if caminho.exists() else (
        "Você transforma um tema em alta num tema de vídeo para um canal de "
        "desenvolvimento pessoal cético e irônico. Responda em pt-BR."
    )

    tema = gerar_tema_de_tendencia("project hail mary", prompt)
    print("tema:", tema.tema)
    print("justificativa:", tema.justificativa)
