"""Checkpoint: reaproveitar artefatos de estágio que já existem e ainda validam.

O maior economizador de custo/tempo do pilar. Cada estágio, antes de pagar por
uma chamada de API, checa se seu artefato já está no disco e válido; se sim (e o
reaproveitamento está ligado), pula a geração. Um run que falhou em uma etapa
posterior, ao ser reexecutado na mesma pasta, reusa os artefatos anteriores em
vez de re-pagar por eles.
"""

from pathlib import Path
from typing import Callable


def artefato_valido(caminho, validar: Callable[[Path], bool] | None = None) -> bool:
    """Diz se um artefato existe e passa numa validação.

    Por padrão: o caminho existe e (se for arquivo) não está vazio. Um `validar`
    opcional adiciona uma checagem específica do estágio (ex.: contagem, formato).
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return False
    if caminho.is_file() and caminho.stat().st_size == 0:
        return False
    return validar is None or bool(validar(caminho))


def todos_validos(caminhos, validar: Callable[[Path], bool] | None = None) -> bool:
    """True se a lista não é vazia e todos os artefatos validam."""
    caminhos = list(caminhos)
    return bool(caminhos) and all(artefato_valido(c, validar) for c in caminhos)


def deve_reaproveitar(
    caminho, reaproveitar: bool, validar: Callable[[Path], bool] | None = None
) -> bool:
    """Combina o toggle de config com a validade do artefato."""
    return bool(reaproveitar) and artefato_valido(caminho, validar)
