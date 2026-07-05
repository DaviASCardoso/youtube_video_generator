"""Gates de qualidade entre estágios — validar o artefato barato antes de pagar o caro.

Generaliza o fail-fast-before-spend já presente no código (`validar_personagens`):
antes de gastar no próximo estágio, confere que o artefato atual está bom. Um gate
que reprova faz o pipeline reexecutar o estágio (ou parar) — nunca deixa um artefato
quebrado chegar a uma etapa cara.

Os gates **estruturais** (não-vazio, contagem 1:1, áudio não-trivial, nº de imagens)
estão sempre ligados. O gate de **tamanho** do roteiro usa os bounds configuráveis
`roteiro.min_palavras`/`max_palavras`, permissivos por padrão (opt-in).
"""

from pathlib import Path


class GateReprovado(Exception):
    """Um artefato de estágio não passou na validação."""


def validar_roteiro(frases: list[tuple[int, str]], cfg_geracao: dict) -> None:
    """Roteiro: não-vazio, sem frase vazia, e dentro dos bounds de tamanho."""
    if not frases:
        raise GateReprovado("roteiro vazio")
    if any(not str(f[1]).strip() for f in frases):
        raise GateReprovado("roteiro contém frase vazia")

    palavras = sum(len(str(f[1]).split()) for f in frases)
    minimo = cfg_geracao["roteiro"]["min_palavras"]
    maximo = cfg_geracao["roteiro"]["max_palavras"]
    if palavras < minimo:
        raise GateReprovado(f"roteiro curto: {palavras} < {minimo} palavras")
    if palavras > maximo:
        raise GateReprovado(f"roteiro longo: {palavras} > {maximo} palavras")


def validar_plano_visual(frases: list, itens_visuais: list) -> None:
    """Plano visual (prompts ou emoção+busca) deve ser 1:1 com as frases."""
    if len(itens_visuais) != len(frases):
        raise GateReprovado(
            f"plano visual {len(itens_visuais)} != {len(frases)} frases"
        )


def validar_narracao(caminho_audio, tamanho_minimo: int = 512) -> None:
    """Narração: arquivo existe e não é trivial/silencioso (bytes acima do mínimo)."""
    caminho = Path(caminho_audio)
    if not caminho.exists():
        raise GateReprovado(f"áudio ausente: {caminho}")
    tamanho = caminho.stat().st_size
    if tamanho < tamanho_minimo:
        raise GateReprovado(f"áudio trivial/silencioso: {tamanho} bytes")


def validar_visuais(caminhos: list, esperado: int) -> None:
    """Visuais: contagem esperada e nenhuma imagem vazia."""
    if len(caminhos) != esperado:
        raise GateReprovado(f"{len(caminhos)} imagens != {esperado} esperadas")
    for c in caminhos:
        p = Path(c)
        if not p.exists() or p.stat().st_size == 0:
            raise GateReprovado(f"imagem inválida: {p}")
