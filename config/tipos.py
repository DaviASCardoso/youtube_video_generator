from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import unicodedata

from config.settings import Config
from config.temas import FilaDeTemas

_TIPOS_DIR = Path(__file__).parent.parent / "tipos"

DEFAULT_CONFIG = {
    "groq": {"modelo": "llama-3.3-70b-versatile", "temperatura": 0.8, "max_tokens": 4096},
    "together": {"modelo": "black-forest-labs/FLUX.2-dev", "steps": 20, "aspect_ratio": "16:9"},
    "tts": {"idioma": "pt-BR", "voz": "pt-BR-Wavenet-B", "velocidade": 1.0, "pitch": 0.0},
    "pipeline": {"min_chars_por_periodo": 20},
    "agendamento": {"frequencia": "daily", "horario": "14:00", "fuso_horario": "America/Sao_Paulo"},
    "youtube": {"categoria_id": "22", "visibilidade": "private", "tags": []},
}

ASSETS_PADRAO = ("system_prompt_script.txt", "system_prompt_prompt.txt", "style_prompt.txt")


@dataclass
class TipoVideo:
    id: str
    nome: str
    ativo: bool
    caminho: Path
    config: Config
    assets_dir: Path
    temas: FilaDeTemas


def _slugify(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = texto.strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    texto = texto.strip("_")
    return texto or "tipo"


def _id_disponivel(id_base: str) -> str:
    if not (_TIPOS_DIR / id_base).exists():
        return id_base

    contador = 2
    while (_TIPOS_DIR / f"{id_base}_{contador}").exists():
        contador += 1
    return f"{id_base}_{contador}"


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


def criar_tipo(nome: str, config_inicial: dict | None = None) -> TipoVideo:
    """Cria um novo tipo de vídeo, com id derivado do nome.

    Args:
        nome: Nome de exibição do tipo.
        config_inicial: Configuração inicial (grupos groq/together/tts/pipeline/
            agendamento/youtube). Grupos/campos ausentes são preenchidos com
            padrões razoáveis a partir de DEFAULT_CONFIG.

    Returns:
        O tipo de vídeo criado.
    """
    id = _id_disponivel(_slugify(nome))
    pasta = _TIPOS_DIR / id
    pasta_assets = pasta / "assets"
    pasta_assets.mkdir(parents=True)

    dados = {**DEFAULT_CONFIG, **(config_inicial or {})}
    dados["nome"] = nome
    dados["ativo"] = dados.get("ativo", True)

    Config(pasta / "config.json").salvar(dados)
    (pasta / "temas.json").write_text("[]", encoding="utf-8")

    for nome_arquivo in ASSETS_PADRAO:
        (pasta_assets / nome_arquivo).write_text("", encoding="utf-8")

    return carregar_tipo(id)


def duplicar_tipo(id_origem: str, novo_nome: str) -> TipoVideo:
    """Duplica um tipo existente (configuração e prompts) com um novo nome/id.

    A fila de temas do novo tipo começa vazia e o novo tipo começa inativo,
    para não disputar o mesmo agendamento/fila do tipo original.

    Args:
        id_origem: Id do tipo a duplicar.
        novo_nome: Nome de exibição do novo tipo.

    Returns:
        O tipo de vídeo criado.
    """
    origem = carregar_tipo(id_origem)
    novo_id = _id_disponivel(_slugify(novo_nome))
    nova_pasta = _TIPOS_DIR / novo_id

    shutil.copytree(origem.assets_dir, nova_pasta / "assets")

    dados = origem.config.get_all()
    dados["nome"] = novo_nome
    dados["ativo"] = False
    Config(nova_pasta / "config.json").salvar(dados)
    (nova_pasta / "temas.json").write_text("[]", encoding="utf-8")

    return carregar_tipo(novo_id)


def renomear_tipo(id_antigo: str, novo_nome: str) -> TipoVideo:
    """Renomeia um tipo: gera um novo id a partir do novo nome e move a pasta se preciso.

    Args:
        id_antigo: Id atual do tipo.
        novo_nome: Novo nome de exibição (usado para derivar o novo id).

    Returns:
        O tipo de vídeo com o id e nome atualizados.

    Raises:
        FileNotFoundError: Se o tipo antigo não existir.
        FileExistsError: Se o novo id já estiver em uso por outro tipo.
    """
    pasta_antiga = _TIPOS_DIR / id_antigo
    if not pasta_antiga.is_dir():
        raise FileNotFoundError(f"Tipo de vídeo '{id_antigo}' não encontrado.")

    novo_id = _slugify(novo_nome)

    if novo_id != id_antigo:
        pasta_nova = _TIPOS_DIR / novo_id
        if pasta_nova.exists():
            raise FileExistsError(f"Já existe um tipo de vídeo com id '{novo_id}'.")
        pasta_antiga.rename(pasta_nova)
    else:
        novo_id = id_antigo

    config = Config((_TIPOS_DIR / novo_id) / "config.json")
    dados = config.get_all()
    dados["nome"] = novo_nome
    config.salvar(dados)

    return carregar_tipo(novo_id)


def excluir_tipo(id: str) -> None:
    """Remove permanentemente um tipo de vídeo e todos os seus dados (config, fila, prompts).

    Args:
        id: Id do tipo a remover.

    Raises:
        FileNotFoundError: Se o tipo não existir.
    """
    pasta = _TIPOS_DIR / id
    if not pasta.is_dir():
        raise FileNotFoundError(f"Tipo de vídeo '{id}' não encontrado.")
    shutil.rmtree(pasta)
