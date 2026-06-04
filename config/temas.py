from pathlib import Path
from datetime import datetime, timezone
import json
import bisect

_TEMAS_PATH = Path(__file__).parent / "temas.json"

def _carregar() -> list[dict]:
    if not _TEMAS_PATH.exists():
        _TEMAS_PATH.write_text("[]", encoding="utf-8")
        return []

    try:
        dados = json.loads(_TEMAS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"temas.json inválido: {e}") from e

    if not isinstance(dados, list):
        raise ValueError("temas.json deve ser uma lista.")

    return dados


def _salvar(temas: list[dict]) -> None:
    _TEMAS_PATH.write_text(
        json.dumps(temas, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def adicionar_tema(
    tema: str,
    prioridade: int,
    fonte: str = "manual",
) -> dict:
    """Adiciona um tema na fila na posição correta pela prioridade (maior = primeiro).

    Args:
        tema: Texto do tema do vídeo.
        prioridade: Valor de 0 a 100. Quanto maior, mais cedo será gerado.
        fonte: Origem do tema ("manual", "trends", "analise", etc).

    Returns:
        O registro do tema adicionado.

    Raises:
        ValueError: Se a prioridade estiver fora do intervalo 0-100.
    """
    if not 0 <= prioridade <= 100:
        raise ValueError(f"Prioridade deve ser entre 0 e 100, recebeu: {prioridade}")

    temas = _carregar()

    registro = {
        "tema": tema,
        "prioridade": prioridade,
        "fonte": fonte,
        "adicionado_em": datetime.now(timezone.utc).isoformat(),
    }

    # bisect trabalha com ordem crescente, então usamos prioridade negativa
    # pra manter o maior no início
    prioridades = [-t["prioridade"] for t in temas]
    posicao = bisect.bisect_right(prioridades, -prioridade)
    temas.insert(posicao, registro)

    _salvar(temas)
    return registro


def proximo_tema() -> str | None:
    """Remove e retorna o tema de maior prioridade da fila.

    Returns:
        Texto do tema, ou None se a fila estiver vazia.
    """
    temas = _carregar()

    if not temas:
        return None

    primeiro = temas.pop(0)
    _salvar(temas)
    return primeiro["tema"]


def listar_temas() -> list[dict]:
    """Retorna todos os temas da fila sem removê-los.

    Returns:
        Lista de registros ordenados por prioridade (maior primeiro).
    """
    return _carregar()


def total() -> int:
    """Retorna a quantidade de temas na fila."""
    return len(_carregar())


def remover_tema(indice: int) -> dict:
    """Remove um tema da fila pelo índice (posição na lista, começando em 0).

    Args:
        indice: Posição do tema na fila.

    Returns:
        O registro removido.

    Raises:
        IndexError: Se o índice estiver fora do range.
    """
    temas = _carregar()

    if indice < 0 or indice >= len(temas):
        raise IndexError(
            f"Índice {indice} fora do range. A fila tem {len(temas)} temas (0 a {len(temas) - 1})."
        )

    removido = temas.pop(indice)
    _salvar(temas)
    return removido


def limpar_fila() -> int:
    """Remove todos os temas da fila.

    Returns:
        Quantidade de temas removidos.
    """
    temas = _carregar()
    quantidade = len(temas)
    _salvar([])
    return quantidade


def alterar_prioridade(indice: int, nova_prioridade: int) -> dict:
    """Altera a prioridade de um tema e reposiciona na fila.

    Args:
        indice: Posição atual do tema na fila.
        nova_prioridade: Novo valor de prioridade (0-100).

    Returns:
        O registro atualizado.

    Raises:
        IndexError: Se o índice estiver fora do range.
        ValueError: Se a prioridade estiver fora do intervalo 0-100.
    """
    if not 0 <= nova_prioridade <= 100:
        raise ValueError(f"Prioridade deve ser entre 0 e 100, recebeu: {nova_prioridade}")

    temas = _carregar()

    if indice < 0 or indice >= len(temas):
        raise IndexError(
            f"Índice {indice} fora do range. A fila tem {len(temas)} temas (0 a {len(temas) - 1})."
        )

    registro = temas.pop(indice)
    registro["prioridade"] = nova_prioridade

    prioridades = [-t["prioridade"] for t in temas]
    nova_posicao = bisect.bisect_right(prioridades, -nova_prioridade)
    temas.insert(nova_posicao, registro)

    _salvar(temas)
    return registro


if __name__ == "__main__":
    # demo rápido
    limpar_fila()

    adicionar_tema("como usar IA para estudar", prioridade=80, fonte="manual")
    adicionar_tema("hábitos de pessoas produtivas", prioridade=50, fonte="trends")
    adicionar_tema("o futuro do mercado de tecnologia", prioridade=95, fonte="analise")
    adicionar_tema("como montar um setup de estudos", prioridade=65, fonte="manual")

    print("=== FILA ATUAL ===")
    for i, t in enumerate(listar_temas()):
        print(f"  [{i}] (p={t['prioridade']}) [{t['fonte']}] {t['tema']}")

    print(f"\nTotal: {total()} temas")
    print(f"\nPróximo: {proximo_tema()}")

    print(f"\n=== APÓS CONSUMIR 1 ===")
    for i, t in enumerate(listar_temas()):
        print(f"  [{i}] (p={t['prioridade']}) [{t['fonte']}] {t['tema']}")