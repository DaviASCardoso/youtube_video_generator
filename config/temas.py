from pathlib import Path
from datetime import datetime, timezone
import json
import bisect


class FilaDeTemas:
    """Fila de temas de um tipo de vídeo, ordenada por prioridade (maior = primeiro),
    persistida em um temas.json.
    """

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)

    def _carregar(self) -> list[dict]:
        if not self._caminho.exists():
            self._caminho.write_text("[]", encoding="utf-8")
            return []

        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{self._caminho.name} inválido: {e}") from e

        if not isinstance(dados, list):
            raise ValueError(f"{self._caminho.name} deve ser uma lista.")

        return dados

    def _salvar(self, temas: list[dict]) -> None:
        self._caminho.write_text(
            json.dumps(temas, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def adicionar(
        self,
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

        temas = self._carregar()

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

        self._salvar(temas)
        return registro

    def proximo(self) -> str | None:
        """Remove e retorna o tema de maior prioridade da fila.

        Returns:
            Texto do tema, ou None se a fila estiver vazia.
        """
        temas = self._carregar()

        if not temas:
            return None

        primeiro = temas.pop(0)
        self._salvar(temas)
        return primeiro["tema"]

    def listar(self) -> list[dict]:
        """Retorna todos os temas da fila sem removê-los.

        Returns:
            Lista de registros ordenados por prioridade (maior primeiro).
        """
        return self._carregar()

    def total(self) -> int:
        """Retorna a quantidade de temas na fila."""
        return len(self._carregar())

    def remover(self, indice: int) -> dict:
        """Remove um tema da fila pelo índice (posição na lista, começando em 0).

        Args:
            indice: Posição do tema na fila.

        Returns:
            O registro removido.

        Raises:
            IndexError: Se o índice estiver fora do range.
        """
        temas = self._carregar()

        if indice < 0 or indice >= len(temas):
            raise IndexError(
                f"Índice {indice} fora do range. A fila tem {len(temas)} temas (0 a {len(temas) - 1})."
            )

        removido = temas.pop(indice)
        self._salvar(temas)
        return removido

    def limpar(self) -> int:
        """Remove todos os temas da fila.

        Returns:
            Quantidade de temas removidos.
        """
        temas = self._carregar()
        quantidade = len(temas)
        self._salvar([])
        return quantidade

    def alterar_prioridade(self, indice: int, nova_prioridade: int) -> dict:
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

        temas = self._carregar()

        if indice < 0 or indice >= len(temas):
            raise IndexError(
                f"Índice {indice} fora do range. A fila tem {len(temas)} temas (0 a {len(temas) - 1})."
            )

        registro = temas.pop(indice)
        registro["prioridade"] = nova_prioridade

        prioridades = [-t["prioridade"] for t in temas]
        nova_posicao = bisect.bisect_right(prioridades, -nova_prioridade)
        temas.insert(nova_posicao, registro)

        self._salvar(temas)
        return registro
