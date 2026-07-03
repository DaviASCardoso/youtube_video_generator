import json

import pytest

from config.settings import Config


def _escrever(tmp_path, dados):
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return caminho


def test_get_aninhado(tmp_path):
    c = Config(_escrever(tmp_path, {"groq": {"modelo": "llama"}}))
    assert c.get("groq.modelo") == "llama"


def test_get_chave_ausente_levanta_keyerror(tmp_path):
    c = Config(_escrever(tmp_path, {"groq": {"modelo": "llama"}}))
    with pytest.raises(KeyError):
        c.get("groq.inexistente")
    with pytest.raises(KeyError):
        c.get("nao.existe")


def test_get_all_retorna_copia(tmp_path):
    c = Config(_escrever(tmp_path, {"a": 1}))
    copia = c.get_all()
    copia["a"] = 999
    assert c.get("a") == 1  # mutar a cópia não afeta o cache interno


def test_salvar_persiste_e_atualiza_cache(tmp_path):
    caminho = _escrever(tmp_path, {"a": 1})
    c = Config(caminho)
    c.get("a")  # popula o cache
    c.salvar({"a": 2, "b": {"c": 3}})
    # em memória
    assert c.get("a") == 2
    assert c.get("b.c") == 3
    # em disco
    em_disco = json.loads(caminho.read_text(encoding="utf-8"))
    assert em_disco == {"a": 2, "b": {"c": 3}}


def test_salvar_rejeita_nao_dicionario(tmp_path):
    c = Config(tmp_path / "c.json")
    with pytest.raises(ValueError):
        c.salvar(["nao", "e", "dict"])


def test_recarregar_le_alteracao_externa(tmp_path):
    caminho = _escrever(tmp_path, {"a": 1})
    c = Config(caminho)
    assert c.get("a") == 1
    caminho.write_text(json.dumps({"a": 42}), encoding="utf-8")
    assert c.get("a") == 1  # ainda em cache
    c.recarregar()
    assert c.get("a") == 42


def test_arquivo_inexistente_levanta(tmp_path):
    c = Config(tmp_path / "nao_existe.json")
    with pytest.raises(FileNotFoundError):
        c.get("qualquer")


def test_json_invalido_levanta_valueerror(tmp_path):
    caminho = tmp_path / "ruim.json"
    caminho.write_text("{ isso nao e json", encoding="utf-8")
    c = Config(caminho)
    with pytest.raises(ValueError):
        c.get("a")
