"""Geração do roteiro + decisão de emoção e termo de busca por frase.

Usado pelo modo de imagens "personagem": a primeira chamada Groq gera o texto
do roteiro (mesmo system prompt/persona do modo "ia"); a segunda, em vez de
gerar prompts de imagem, decide para cada frase uma EMOÇÃO do personagem e um
TERMO DE BUSCA em inglês para achar a foto de fundo no Pexels. As instruções
dessa segunda chamada vivem em tipos/<id>/assets/system_prompt_cena.txt,
editável no painel como os demais prompts.
"""

from pathlib import Path

from config.settings import Config
from scripts.compositor import EMOCAO_PADRAO, EMOCOES
from scripts.generate_script import _chamar_api, _parsear_prompts, _separar_periodos

_EMOCOES_VALIDAS = set(EMOCOES)


def _normalizar(cena: dict) -> tuple[str, str]:
    """Valida uma entrada do modelo, com fallback seguro para não quebrar o vídeo."""
    emocao = str(cena.get("emocao", "")).strip().lower()
    if emocao not in _EMOCOES_VALIDAS:
        emocao = EMOCAO_PADRAO

    busca = str(cena.get("busca", "")).strip()
    if not busca:
        busca = "abstract textured background"

    return emocao, busca


def gerar_cenas(
    prompt: str, config: Config, assets_dir: Path
) -> list[tuple[int, str, str, str]]:
    """Gera o roteiro e decide emoção + busca para cada frase.

    Returns:
        Lista de (indice, frase, emocao, termo_busca), 1:1 com as frases do
        roteiro — mesma invariante de contagem do modo "ia".
    """
    system_prompt_script = (
        (assets_dir / "system_prompt_script.txt").read_text(encoding="utf-8").strip()
    )
    roteiro = _chamar_api(system_prompt_script, prompt, config)

    frases = _separar_periodos(roteiro, config.get("pipeline.min_chars_por_periodo"))

    system_prompt_cena = (
        (assets_dir / "system_prompt_cena.txt").read_text(encoding="utf-8").strip()
    )
    numeradas = "\n".join(f"{i}. {f}" for i, f in enumerate(frases, start=1))
    resposta = _chamar_api(system_prompt_cena, numeradas, config)
    cenas = _parsear_prompts(resposta)  # array JSON -> list[dict]

    resultado = []
    for i, frase in enumerate(frases):
        cena = cenas[i] if i < len(cenas) and isinstance(cenas[i], dict) else {}
        emocao, busca = _normalizar(cena)
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
