from pathlib import Path
import json


class Config:
    """Configuração de um tipo de vídeo, carregada de um config.json.

    Suporta acesso aninhado com ponto: config.get("groq.modelo")
    """

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)
        self._config: dict | None = None

    def _carregar(self) -> dict:
        if self._config is not None:
            return self._config

        if not self._caminho.exists():
            raise FileNotFoundError(
                f"Arquivo de configuração não encontrado: {self._caminho}"
            )

        try:
            self._config = json.loads(self._caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{self._caminho.name} inválido: {e}") from e

        return self._config

    def get(self, chave: str) -> str | int | float | bool | dict | list:
        """Retorna o valor de uma configuração pelo nome da chave.

        Args:
            chave: Nome da configuração, com suporte a notação de ponto para aninhamento.

        Returns:
            Valor da configuração.

        Raises:
            KeyError: Se a chave não existir no config.json.
        """
        config = self._carregar()
        partes = chave.split(".")
        valor = config

        for parte in partes:
            if not isinstance(valor, dict) or parte not in valor:
                raise KeyError(
                    f"Configuração '{chave}' não encontrada em {self._caminho}.\n"
                    f"Chave ausente: '{parte}'"
                )
            valor = valor[parte]

        return valor

    def get_all(self) -> dict:
        """Retorna todas as configurações como dicionário."""
        return self._carregar().copy()

    def salvar(self, dados: dict) -> None:
        """Substitui e persiste a configuração inteira em disco.

        Args:
            dados: Novo conteúdo completo do config.json.

        Raises:
            ValueError: Se dados não for um dicionário.
        """
        if not isinstance(dados, dict):
            raise ValueError("Configuração deve ser um dicionário.")

        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._config = dados

    def recarregar(self) -> None:
        """Força o recarregamento do config.json do disco.
        Útil quando o arquivo é editado durante a execução.
        """
        self._config = None
        self._carregar()
