"""Geração do roteiro + decisão de emoção, termo de busca e ícone por frase.

Usado pelo modo de imagens "personagem": a primeira chamada Groq gera o texto
do roteiro (mesmo system prompt/persona do modo "ia"); a segunda, em vez de
gerar prompts de imagem, decide para cada frase três coisas: a EMOÇÃO do
personagem, um TERMO DE BUSCA em inglês para achar a foto de fundo no Pexels e um
CONCEITO DE ÍCONE (um substantivo em inglês, ou None quando nenhum ícone serve).
As instruções dessa segunda chamada vivem em tipos/<id>/assets/system_prompt_cena.txt,
editável no painel como os demais prompts.
"""

import re
from pathlib import Path

from config.settings import Config
from feedback import guia
from geracao.compositor import EMOCAO_PADRAO, EMOCOES
from geracao.custo import CUSTO_GROQ_CHAMADA
from geracao.generate_script import _chamar_api, _parsear_prompts, _separar_periodos

_EMOCOES_VALIDAS = set(EMOCOES)

# Valores que o modelo pode devolver querendo dizer "sem ícone" — todos viram None.
_ICONE_VAZIO = {"", "null", "none", "nenhum", "nao", "não", "n/a", "na", "-"}


def _normalizar_icone(valor) -> str | None:
    """Coage o campo `icone` do modelo num conceito curto (1–2 palavras, minúsculo)
    ou None. Qualquer coisa malformada (não-string, vazio, "null", só pontuação)
    vira None, para a cena degradar para "sem ícone" em vez de quebrar."""
    if not isinstance(valor, str):
        return None
    conceito = valor.strip().lower()
    if conceito in _ICONE_VAZIO:
        return None
    palavras = re.findall(r"[a-z]+", conceito)
    if not palavras:
        return None
    return " ".join(palavras[:2])


def _normalizar(cena: dict) -> tuple[str, str, str | None]:
    """Valida uma entrada do modelo, com fallback seguro para não quebrar o vídeo.

    Returns:
        (emocao, busca, icone) — `icone` é um conceito minúsculo ou None (sem ícone).
    """
    emocao = str(cena.get("emocao", "")).strip().lower()
    if emocao not in _EMOCOES_VALIDAS:
        emocao = EMOCAO_PADRAO

    busca = str(cena.get("busca", "")).strip()
    if not busca:
        busca = "abstract textured background"

    icone = _normalizar_icone(cena.get("icone"))

    return emocao, busca, icone


def _planejar_cenas(frases: list, config: Config, assets_dir: Path, ledger, estagio_custo: str) -> list[tuple[str, str, str | None]]:
    """Faz a chamada de cena (system_prompt_cena.txt) e devolve os três fatores por
    frase normalizados (emoção, busca, ícone), 1:1 com `frases`. Base compartilhada
    das camadas independentes (personagem e ícone) quando o fundo é por IA."""
    system = guia.compor(
        assets_dir, "visual",
        (Path(assets_dir) / "system_prompt_cena.txt").read_text(encoding="utf-8").strip(),
    )
    numeradas = "\n".join(f"{i}. {frase}" for i, frase in frases)
    resposta = _chamar_api(system, numeradas, config)
    cenas = _parsear_prompts(resposta)

    if ledger is not None:
        ledger.registrar(
            estagio_custo, "groq", CUSTO_GROQ_CHAMADA, modelo=config.get("groq.modelo")
        )

    resultado = []
    for i in range(len(frases)):
        cena = cenas[i] if i < len(cenas) and isinstance(cenas[i], dict) else {}
        resultado.append(_normalizar(cena))
    return resultado


def planejar_emocoes(frases: list, config: Config, assets_dir: Path, ledger=None) -> list[str]:
    """Emoção do personagem por frase — a **camada de personagem**, independente da
    fonte do fundo.

    Faz a mesma chamada de cena (system_prompt_cena.txt), mas só aproveita a emoção
    (a busca é assunto do fundo Pexels e o ícone é assunto da camada de ícones — ambos
    ignorados aqui). Assim um fundo por IA também pode ter um personagem que muda de
    expressão a cada cena — sem acoplar a emoção à foto de banco.

    Args:
        frases: Lista de (indice, frase) do roteiro.

    Returns:
        Uma emoção por frase (1:1), normalizada (emoção desconhecida -> neutro).
    """
    return [emocao for emocao, _, _ in _planejar_cenas(frases, config, assets_dir, ledger, "plano_personagem")]


def planejar_icones(frases: list, config: Config, assets_dir: Path, ledger=None) -> list[str | None]:
    """Conceito de ícone por frase — a **camada de ícones**, independente do fundo e
    do personagem.

    Faz a mesma chamada de cena (system_prompt_cena.txt) e aproveita só o `icone`
    (a emoção é da camada de personagem e a busca do fundo Pexels). Usada quando o
    fundo é por IA e a camada de ícones está ligada — para um fundo por IA também
    poder mostrar um ícone por cena.

    Returns:
        Um conceito de ícone por frase (1:1) — string minúscula ou None (sem ícone).
    """
    return [icone for _, _, icone in _planejar_cenas(frases, config, assets_dir, ledger, "plano_icone")]


def gerar_cenas(
    prompt: str, config: Config, assets_dir: Path
) -> list[tuple[int, str, str, str, str | None]]:
    """Gera o roteiro e decide emoção + busca + ícone para cada frase.

    Returns:
        Lista de (indice, frase, emocao, termo_busca, icone), 1:1 com as frases do
        roteiro — mesma invariante de contagem do modo "ia". `icone` é um conceito
        minúsculo ou None (sem ícone).
    """
    system_prompt_script = guia.compor(
        assets_dir, "roteiro",
        (assets_dir / "system_prompt_script.txt").read_text(encoding="utf-8").strip(),
    )
    roteiro = _chamar_api(system_prompt_script, prompt, config)

    frases = _separar_periodos(roteiro, config.get("pipeline.min_chars_por_periodo"))

    system_prompt_cena = guia.compor(
        assets_dir, "visual",
        (assets_dir / "system_prompt_cena.txt").read_text(encoding="utf-8").strip(),
    )
    numeradas = "\n".join(f"{i}. {f}" for i, f in enumerate(frases, start=1))
    resposta = _chamar_api(system_prompt_cena, numeradas, config)
    cenas = _parsear_prompts(resposta)  # array JSON -> list[dict]

    resultado = []
    for i, frase in enumerate(frases):
        cena = cenas[i] if i < len(cenas) and isinstance(cenas[i], dict) else {}
        emocao, busca, icone = _normalizar(cena)
        resultado.append((i + 1, frase, emocao, busca, icone))

    return resultado


if __name__ == "__main__":
    from config.tipos import carregar_tipo

    tipo = carregar_tipo("cetico_pratico")
    cenas = gerar_cenas(
        "Gere um roteiro sobre dicas de produtividade para estudantes",
        tipo.config,
        tipo.assets_dir,
    )
    for indice, frase, emocao, busca, icone in cenas:
        print(f"{indice:2d}. [{emocao:9s}] busca='{busca}' icone={icone!r}  | {frase}")
