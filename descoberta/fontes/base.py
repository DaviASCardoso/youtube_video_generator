"""Contrato comum das fontes de sinal + registro nome→função.

Uma fonte é qualquer coisa que proponha candidatos a tema. Cada módulo de fonte
registra sua função `buscar(tipo, cfg_fonte) -> list[Candidato]` com o decorator
`@registrar("nome")`. O orquestrador itera só as fontes ativas e chama `coletar`,
que centraliza a postura **degrade-instead-of-crash**: uma fonte que falha (rede,
chave ausente, dependência frágil) devolve nada e é pulada, nunca quebra o ciclo.
"""

from typing import TYPE_CHECKING, Callable

from descoberta.candidato import Candidato, agora, forca_por_posicao

if TYPE_CHECKING:
    from config.tipos import TipoVideo

_REGISTRO: dict[str, Callable] = {}


def registrar(nome: str):
    """Decorator: registra a função `buscar` de uma fonte sob um nome."""

    def _decorator(func: Callable) -> Callable:
        _REGISTRO[nome] = func
        return func

    return _decorator


def registrada(nome: str) -> bool:
    return nome in _REGISTRO


def coletar(nome: str, tipo: "TipoVideo", cfg_fonte: dict) -> list[Candidato]:
    """Coleta candidatos de uma fonte pelo nome, tolerando qualquer falha.

    Returns:
        Lista de candidatos, ou lista vazia se a fonte é desconhecida, está
        desativada implicitamente, ou levantou qualquer exceção.
    """
    func = _REGISTRO.get(nome)
    if func is None:
        print(f"    [descoberta] fonte desconhecida: {nome}")
        return []
    try:
        return list(func(tipo, cfg_fonte) or [])
    except Exception as e:
        print(f"    [descoberta:{nome}] falhou, pulando: {e}")
        return []


def candidatos_por_rank(
    textos: list[str], fonte: str, categoria: str = "trending"
) -> list[Candidato]:
    """Constrói candidatos a partir de textos já em ordem de ranking.

    Limpa vazios/não-strings e atribui `forca_sinal` pela posição (topo = mais
    forte). Todas as fontes que só sabem ordenar usam este atalho.
    """
    limpos = [t.strip() for t in textos if isinstance(t, str) and t.strip()]
    total = len(limpos)
    quando = agora()
    return [
        Candidato(
            texto=texto,
            fonte=fonte,
            forca_sinal=forca_por_posicao(i, total),
            observado_em=quando,
            categoria=categoria,
        )
        for i, texto in enumerate(limpos)
    ]
