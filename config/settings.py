from pathlib import Path
import json

_CONFIG_PATH = Path(__file__).parent / "config.json"
_config: dict | None = None


def _carregar() -> dict:
    global _config
    if _config is not None:
        return _config

    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {_CONFIG_PATH}\n"
            "Crie o arquivo config/config.json antes de executar o pipeline."
        )

    try:
        _config = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"config.json inválido: {e}") from e

    return _config


def get(chave: str) -> str | int | float | bool | dict | list:
    """Retorna o valor de uma configuração pelo nome da chave.

    Suporta acesso aninhado com ponto: get("groq.modelo")

    Args:
        chave: Nome da configuração, com suporte a notação de ponto para aninhamento.

    Returns:
        Valor da configuração.

    Raises:
        KeyError: Se a chave não existir no config.json.
    """
    config = _carregar()
    partes = chave.split(".")
    valor = config

    for parte in partes:
        if not isinstance(valor, dict) or parte not in valor:
            raise KeyError(
                f"Configuração '{chave}' não encontrada no config.json.\n"
                f"Chave ausente: '{parte}'"
            )
        valor = valor[parte]

    return valor


def get_all() -> dict:
    """Retorna todas as configurações como dicionário."""
    return _carregar().copy()


def recarregar() -> None:
    """Força o recarregamento do config.json do disco.
    Útil quando o arquivo é editado durante a execução.
    """
    global _config
    _config = None
    _carregar()
