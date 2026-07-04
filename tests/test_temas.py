import json

import pytest

from descoberta.temas import FilaDeTemas


@pytest.fixture
def fila(tmp_path):
    return FilaDeTemas(tmp_path / "temas.json")


def test_adicionar_ordena_por_prioridade(fila):
    fila.adicionar("baixa", 10)
    fila.adicionar("alta", 90)
    fila.adicionar("media", 50)
    temas = [t["tema"] for t in fila.listar()]
    assert temas == ["alta", "media", "baixa"]


def test_registro_tem_campos_esperados(fila):
    reg = fila.adicionar("um tema", 70, fonte="trends")
    assert reg["tema"] == "um tema"
    assert reg["prioridade"] == 70
    assert reg["fonte"] == "trends"
    assert "adicionado_em" in reg


def test_proximo_remove_maior_prioridade(fila):
    fila.adicionar("baixa", 10)
    fila.adicionar("alta", 90)
    assert fila.proximo() == "alta"
    assert fila.total() == 1
    assert fila.proximo() == "baixa"
    assert fila.proximo() is None  # fila vazia


def test_prioridade_fora_do_intervalo_nao_escreve_arquivo(tmp_path):
    caminho = tmp_path / "temas.json"
    fila = FilaDeTemas(caminho)
    with pytest.raises(ValueError):
        fila.adicionar("x", 101)
    with pytest.raises(ValueError):
        fila.adicionar("x", -1)
    # a validação acontece antes de tocar no disco
    assert not caminho.exists()


def test_remover_por_indice(fila):
    fila.adicionar("a", 30)
    fila.adicionar("b", 20)
    removido = fila.remover(0)
    assert removido["tema"] == "a"
    assert [t["tema"] for t in fila.listar()] == ["b"]


def test_remover_indice_invalido(fila):
    fila.adicionar("a", 30)
    with pytest.raises(IndexError):
        fila.remover(5)


def test_limpar_retorna_quantidade(fila):
    fila.adicionar("a", 10)
    fila.adicionar("b", 20)
    assert fila.limpar() == 2
    assert fila.total() == 0


def test_alterar_prioridade_reordena(fila):
    fila.adicionar("a", 30)
    fila.adicionar("b", 20)
    # sobe "b" para o topo
    fila.alterar_prioridade(1, 90)
    assert [t["tema"] for t in fila.listar()] == ["b", "a"]


def test_alterar_prioridade_valida_intervalo(fila):
    fila.adicionar("a", 30)
    with pytest.raises(ValueError):
        fila.alterar_prioridade(0, 200)


def test_carregar_cria_arquivo_vazio(tmp_path):
    caminho = tmp_path / "temas.json"
    fila = FilaDeTemas(caminho)
    assert fila.listar() == []
    assert caminho.exists()
    assert json.loads(caminho.read_text(encoding="utf-8")) == []
