from groq import Groq
from dotenv import load_dotenv
from pathlib import Path
from config.settings import Config
from feedback import guia
import os
import json
import re

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

API_KEY = os.getenv("GROQ_API_KEY")


def _chamar_api(system_prompt: str, user_prompt: str, config: Config) -> str:
    cliente = Groq(api_key=API_KEY)
    resposta = cliente.chat.completions.create(
        model=config.get("groq.modelo"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=config.get("groq.temperatura"),
        max_tokens=config.get("groq.max_tokens"),
    )
    return resposta.choices[0].message.content.strip()


def _separar_periodos(texto: str, min_chars: int) -> list[str]:
    partes = re.split(r'(?<=[.!?…])\s+', texto.strip())
    partes = [p.strip() for p in partes if p.strip()]

    frases = []
    acumulado = ""

    for parte in partes:
        if not acumulado:
            acumulado = parte
        elif len(acumulado) < min_chars:
            acumulado += " " + parte
        else:
            frases.append(acumulado)
            acumulado = parte

    if acumulado:
        if frases and len(acumulado) < min_chars:
            frases[-1] += " " + acumulado
        else:
            frases.append(acumulado)

    return frases


def _parsear_prompts(resposta: str) -> list[str]:
    resposta = re.sub(r"```(?:json)?\s*", "", resposta).strip().rstrip("`").strip()
    return json.loads(resposta)


def gerar_roteiro(
    prompt: str, config: Config, assets_dir: Path
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    system_prompt_script = guia.compor(
        assets_dir, "roteiro",
        (assets_dir / "system_prompt_script.txt").read_text(encoding="utf-8").strip(),
    )
    system_prompt_prompt = guia.compor(
        assets_dir, "visual",
        (assets_dir / "system_prompt_prompt.txt").read_text(encoding="utf-8").strip(),
    )

    roteiro = _chamar_api(system_prompt_script, prompt, config)

    frases = _separar_periodos(roteiro, config.get("pipeline.min_chars_por_periodo"))
    frases_tuplas = [(i + 1, frase) for i, frase in enumerate(frases)]

    frases_numeradas = "\n".join(f"{i}. {frase}" for i, frase in frases_tuplas)
    resposta_prompts = _chamar_api(system_prompt_prompt, frases_numeradas, config)
    lista_prompts = _parsear_prompts(resposta_prompts)

    prompts_tuplas = [(i + 1, p) for i, p in enumerate(lista_prompts)]

    return frases_tuplas, prompts_tuplas


if __name__ == "__main__":
    from config.tipos import carregar_tipo

    tipo = carregar_tipo("cetico_pratico")
    frases, prompts_imagem = gerar_roteiro(
        "Dicas de produtividade para estudantes", tipo.config, tipo.assets_dir
    )

    print("=== FRASES ===")
    for item in frases:
        print(item)

    print("\n=== PROMPTS DE IMAGEM ===")
    for item in prompts_imagem:
        print(item)