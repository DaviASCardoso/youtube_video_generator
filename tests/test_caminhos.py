"""Testes da resolução/criação/verificação das raízes de armazenamento."""

import json

import pytest

from config import caminhos


@pytest.fixture
def config_caminhos(monkeypatch):
    """Aponta a config do sistema para valores conhecidos (exercita a indireção real)."""
    from config.sistema import sistema

    def _definir(valores: dict):
        monkeypatch.setattr(sistema, "_config", json.loads(json.dumps(valores)))

    return _definir


def test_raiz_relativa_ancora_na_raiz_do_repo(config_caminhos):
    config_caminhos({"saida": {"pasta_base": "output"}})
    esperado = caminhos._REPO / "output"
    assert caminhos.raiz("saida") == esperado
    assert caminhos.raiz("saida").is_absolute()


def test_raiz_absoluta_usada_como_esta(config_caminhos, tmp_path):
    destino = tmp_path / "nas" / "execucoes"
    config_caminhos({"caminhos": {"execucoes": str(destino)}})
    assert caminhos.raiz("execucoes") == destino


def test_raiz_cai_no_padrao_quando_config_ausente(config_caminhos):
    # Sem bloco `caminhos` no config, cada raiz cai no local de hoje.
    config_caminhos({"saida": {"pasta_base": "output"}})
    assert caminhos.raiz("execucoes") == caminhos._REPO / "execucoes"
    assert caminhos.raiz("tendencias") == caminhos._REPO / "tendencias"
    assert caminhos.raiz("tipos") == caminhos._REPO / "tipos"


def test_raiz_vazia_cai_no_padrao(config_caminhos):
    config_caminhos({"caminhos": {"tipos": "   "}})
    assert caminhos.raiz("tipos") == caminhos._REPO / "tipos"


def test_raiz_desconhecida_levanta(config_caminhos):
    config_caminhos({})
    with pytest.raises(KeyError):
        caminhos.raiz("inexistente")


def test_garantir_raizes_cria_arvore(config_caminhos, tmp_path):
    config_caminhos(
        {
            "saida": {"pasta_base": str(tmp_path / "out")},
            "caminhos": {
                "execucoes": str(tmp_path / "exec"),
                "tendencias": str(tmp_path / "tend"),
                "tipos": str(tmp_path / "tp"),
            },
        }
    )
    problemas = caminhos.garantir_raizes()
    assert problemas == []
    for sub in ("out", "exec", "tend", "tp"):
        assert (tmp_path / sub).is_dir()


def test_verificar_raiz_sinaliza_indisponivel(config_caminhos, tmp_path, monkeypatch):
    destino = tmp_path / "nas_offline"
    config_caminhos({"caminhos": {"execucoes": str(destino)}})

    # Simula um mount ausente/somente-leitura: a criação da árvore falha.
    def _mkdir_falha(self, *a, **k):
        raise OSError("mount indisponível")

    monkeypatch.setattr("pathlib.Path.mkdir", _mkdir_falha)
    estado = caminhos.verificar_raiz("execucoes")
    assert estado["ok"] is False
    assert estado["gravavel"] is False
    assert estado["nome"] == "execucoes"

    problemas = caminhos.garantir_raizes()
    nomes = {p["nome"] for p in problemas}
    assert "execucoes" in nomes
    assert "não gravável" in caminhos.mensagem_problemas(problemas)
