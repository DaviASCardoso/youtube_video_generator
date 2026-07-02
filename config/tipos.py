from dataclasses import dataclass
from pathlib import Path

from config.settings import Config
from config.temas import FilaDeTemas

_TIPOS_DIR = Path(__file__).parent.parent / "tipos"


@dataclass
class TipoVideo:
    id: str
    nome: str
    ativo: bool
    caminho: Path
    config: Config
    assets_dir: Path
    temas: FilaDeTemas


def carregar_tipo(id: str) -> TipoVideo:
    """Carrega um tipo de vídeo pelo id (nome da pasta em tipos/).

    Args:
        id: Nome da pasta do tipo, em tipos/<id>/.

    Returns:
        O tipo de vídeo carregado.

    Raises:
        FileNotFoundError: Se tipos/<id>/config.json não existir.
    """
    caminho = _TIPOS_DIR / id
    config = Config(caminho / "config.json")

    return TipoVideo(
        id=id,
        nome=config.get("nome"),
        ativo=config.get("ativo"),
        caminho=caminho,
        config=config,
        assets_dir=caminho / "assets",
        temas=FilaDeTemas(caminho / "temas.json"),
    )


def listar_tipos() -> list[TipoVideo]:
    """Lista todos os tipos de vídeo encontrados em tipos/.

    Returns:
        Lista de tipos de vídeo, na ordem em que as pastas aparecem no disco.
    """
    if not _TIPOS_DIR.exists():
        return []

    ids = sorted(
        p.parent.name for p in _TIPOS_DIR.glob("*/config.json")
    )
    return [carregar_tipo(id) for id in ids]


def listar_tipos_ativos() -> list[TipoVideo]:
    """Lista apenas os tipos de vídeo marcados como ativos."""
    return [tipo for tipo in listar_tipos() if tipo.ativo]
