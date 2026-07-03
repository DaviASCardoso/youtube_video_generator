import json

import pytest

from config import tipos as tipos_mod
from config.tipos import (
    ASSETS_PADRAO,
    _slugify,
    carregar_tipo,
    criar_tipo,
    duplicar_tipo,
    excluir_tipo,
    listar_tipos,
    listar_tipos_ativos,
    renomear_tipo,
)


def test_slugify():
    assert _slugify("Cético Prático") == "cetico_pratico"
    assert _slugify("  Olá,  Mundo!! ") == "ola_mundo"
    assert _slugify("já é ") == "ja_e"
    assert _slugify("!!!") == "tipo"  # fallback quando nada sobra


def test_id_disponivel_evita_colisao(tipos_dir):
    (tipos_dir / "canal").mkdir()
    assert tipos_mod._id_disponivel("canal") == "canal_2"
    (tipos_dir / "canal_2").mkdir()
    assert tipos_mod._id_disponivel("canal") == "canal_3"
    assert tipos_mod._id_disponivel("outro") == "outro"


def test_criar_tipo_comeca_inativo_com_assets(tipos_dir):
    tipo = criar_tipo("Meu Canal")
    assert tipo.id == "meu_canal"
    assert tipo.ativo is False  # recém-criado não deve ser pego pelo cron
    # assets padrão criados e vazios
    for nome in ASSETS_PADRAO:
        caminho = tipo.assets_dir / nome
        assert caminho.exists()
        assert caminho.read_text(encoding="utf-8") == ""
    # fila de temas vazia
    assert json.loads((tipo.caminho / "temas.json").read_text(encoding="utf-8")) == []
    assert tipo.temas.total() == 0


def test_criar_tipo_merge_config_inicial(tipos_dir):
    tipo = criar_tipo("X", config_inicial={"tts": {"idioma": "en-US", "voz": "v", "velocidade": 1.0, "pitch": 0.0}})
    assert tipo.config.get("tts.idioma") == "en-US"
    # campos não informados vêm do DEFAULT_CONFIG
    assert tipo.config.get("groq.modelo")


def test_duplicar_tipo_inativo_e_fila_vazia(tipos_dir):
    origem = criar_tipo("Origem")
    origem.temas.adicionar("um tema", 50)
    # ativa a origem para provar que a cópia NÃO herda ativo
    dados = origem.config.get_all()
    dados["ativo"] = True
    origem.config.salvar(dados)

    copia = duplicar_tipo("origem", "Cópia")
    assert copia.id == "copia"
    assert copia.ativo is False
    assert copia.temas.total() == 0  # não herda a fila da origem


def test_renomear_move_pasta_e_atualiza_nome(tipos_dir):
    criar_tipo("Antigo")
    novo = renomear_tipo("antigo", "Novo Nome")
    assert novo.id == "novo_nome"
    assert novo.nome == "Novo Nome"
    assert not (tipos_dir / "antigo").exists()
    assert (tipos_dir / "novo_nome").exists()


def test_renomear_colisao_levanta(tipos_dir):
    criar_tipo("Um")
    criar_tipo("Dois")
    with pytest.raises(FileExistsError):
        renomear_tipo("um", "Dois")


def test_excluir_remove_pasta(tipos_dir):
    criar_tipo("Temp")
    assert (tipos_dir / "temp").exists()
    excluir_tipo("temp")
    assert not (tipos_dir / "temp").exists()


def test_excluir_inexistente_levanta(tipos_dir):
    with pytest.raises(FileNotFoundError):
        excluir_tipo("nao_existe")


def test_listar_e_listar_ativos(tipos_dir):
    a = criar_tipo("A")  # inativo
    b = criar_tipo("B")
    # ativa B
    dados = b.config.get_all()
    dados["ativo"] = True
    b.config.salvar(dados)

    ids = [t.id for t in listar_tipos()]
    assert ids == ["a", "b"]  # ordenado por nome de pasta
    ativos = [t.id for t in listar_tipos_ativos()]
    assert ativos == ["b"]


def test_carregar_tipo_inexistente_levanta(tipos_dir):
    with pytest.raises(FileNotFoundError):
        carregar_tipo("fantasma")
