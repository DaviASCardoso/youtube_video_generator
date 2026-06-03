from groq import Groq
from dotenv import load_dotenv
from pathlib import Path
import os
import json
import re

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

API_KEY = os.getenv("GROQ_API_KEY")
MODELO = "llama-3.3-70b-versatile"

ASSETS = BASE.parent / "assets"
SYSTEM_PROMPT_SCRIPT = (ASSETS / "system_prompt_script.txt").read_text(encoding="utf-8").strip()
SYSTEM_PROMPT_PROMPTS = (ASSETS / "system_prompt_prompt.txt").read_text(encoding="utf-8").strip()

MIN_CHARS = 20


def _chamar_api(system_prompt: str, user_prompt: str) -> str:
    cliente = Groq(api_key=API_KEY)
    resposta = cliente.chat.completions.create(
        model=MODELO,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=4096,
    )
    return resposta.choices[0].message.content.strip()


def _separar_periodos(texto: str) -> list[str]:
    # separa por ponto, reticências, exclamação e interrogação
    partes = re.split(r'(?<=[.!?…])\s+', texto.strip())
    partes = [p.strip() for p in partes if p.strip()]

    frases = []
    acumulado = ""

    for parte in partes:
        if not acumulado:
            acumulado = parte
        elif len(acumulado) < MIN_CHARS:
            acumulado += " " + parte
        else:
            frases.append(acumulado)
            acumulado = parte

    if acumulado:
        # se o último também for curto, junta com o anterior
        if frases and len(acumulado) < MIN_CHARS:
            frases[-1] += " " + acumulado
        else:
            frases.append(acumulado)

    return frases


def _parsear_prompts(resposta: str) -> list[str]:
    # remove blocos markdown se houver
    resposta = re.sub(r"```(?:json)?\s*", "", resposta).strip().rstrip("`").strip()
    return json.loads(resposta)


def gerar_roteiro(prompt: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    # etapa 1: gera o roteiro em parágrafo
    roteiro = _chamar_api(SYSTEM_PROMPT_SCRIPT, prompt)

    # etapa 2: separa em períodos com critério de tamanho
    frases = _separar_periodos(roteiro)
    frases_tuplas = [(i + 1, frase) for i, frase in enumerate(frases)]

    # etapa 3: gera os prompts de imagem para cada frase
    frases_numeradas = "\n".join(f"{i}. {frase}" for i, frase in frases_tuplas)
    resposta_prompts = _chamar_api(SYSTEM_PROMPT_PROMPTS, frases_numeradas)
    lista_prompts = _parsear_prompts(resposta_prompts)

    prompts_tuplas = [(i + 1, p) for i, p in enumerate(lista_prompts)]

    return frases_tuplas, prompts_tuplas


if __name__ == "__main__":
    frases, prompts_imagem = gerar_roteiro("Dicas de produtividade para estudantes")

    print("=== FRASES ===")
    for item in frases:
        print(item)

    print("\n=== PROMPTS DE IMAGEM ===")
    for item in prompts_imagem:
        print(item)