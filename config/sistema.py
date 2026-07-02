from pathlib import Path

from config.settings import Config

_CAMINHO = Path(__file__).parent / "sistema.json"

sistema = Config(_CAMINHO)
