"""Geração do roteiro + decisão de emoção e termo de busca por frase.

Reaproveita as chamadas Groq já existentes (`geracao.generate_script`): a
primeira gera o texto do roteiro (mesmo system prompt/persona de sempre); a
segunda, em vez de gerar prompts de imagem, decide para cada frase uma EMOÇÃO
do personagem e um TERMO DE BUSCA em inglês para o fundo no Pexels.
"""

from pathlib import Path

from config.settings import Config
from geracao.generate_script import _chamar_api, _parsear_prompts, _separar_periodos

from prototipo_personagem.compositor import EMOCAO_PADRAO, EMOCOES

BASE = Path(__file__).parent
EMOCOES_VALIDAS = set(EMOCOES)


def _normalizar(cena: dict, frase: str) -> tuple[str, str]:
    """Valida uma entrada do modelo, com fallback seguro para não quebrar o vídeo."""
    emocao = str(cena.get("emocao", "")).strip().lower()
    if emocao not in EMOCOES_VALIDAS:
        emocao = EMOCAO_PADRAO

    busca = str(cena.get("busca", "")).strip()
    if not busca:
        busca = "abstract textured background"

    return emocao, busca


def gerar_cenas(
    prompt: str, config: Config, assets_dir: Path
) -> list[tuple[int, str, str, str]]:
    """Retorna uma lista de (indice, frase, emocao, termo_busca), 1:1 com as frases."""
    system_prompt_script = (
        (assets_dir / "system_prompt_script.txt").read_text(encoding="utf-8").strip()
    )
    roteiro = _chamar_api(system_prompt_script, prompt, config)

    frases = _separar_periodos(roteiro, config.get("pipeline.min_chars_por_periodo"))

    system_prompt_cena = (BASE / "system_prompt_cena.txt").read_text(encoding="utf-8").strip()
    numeradas = "\n".join(f"{i}. {f}" for i, f in enumerate(frases, start=1))
    resposta = _chamar_api(system_prompt_cena, numeradas, config)
    cenas = _parsear_prompts(resposta)  # array JSON -> list[dict]

    resultado = []
    for i, frase in enumerate(frases):
        cena = cenas[i] if i < len(cenas) and isinstance(cenas[i], dict) else {}
        emocao, busca = _normalizar(cena, frase)
        resultado.append((i + 1, frase, emocao, busca))

    return resultado


if __name__ == "__main__":
    from config.tipos import carregar_tipo

    tipo = carregar_tipo("cetico_pratico")
    cenas = gerar_cenas(
        "Gere um roteiro sobre dicas de produtividade para estudantes",
        tipo.config,
        tipo.assets_dir,
    )
    for indice, frase, emocao, busca in cenas:
        print(f"{indice:2d}. [{emocao:9s}] busca='{busca}'  | {frase}")
