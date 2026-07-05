import json

from geracao.custo import CUSTO_GROQ_CHAMADA, Ledger
from publicacao import metadados, registro


def _mock_chamar(monkeypatch, resposta):
    monkeypatch.setattr("publicacao.metadados._chamar_api", lambda s, u, c: resposta)


def test_gerar_metadados_feliz(make_tipo, monkeypatch):
    tipo = make_tipo()
    _mock_chamar(
        monkeypatch,
        json.dumps({"titulo": "Título Otimizado", "descricao": "Desc.", "tags": ["a", "b"]}),
    )
    led = Ledger()
    out = metadados.gerar_metadados(
        {"tema": "tema cru", "roteiro": "o roteiro"}, tipo.config, tipo.assets_dir, ledger=led
    )
    assert out == {"titulo": "Título Otimizado", "descricao": "Desc.", "tags": ["a", "b"]}
    assert led.total() == CUSTO_GROQ_CHAMADA
    assert led.provedores()["metadados"] == "groq"


def test_gerar_metadados_degrada_para_tema_cru(make_tipo, monkeypatch):
    tipo = make_tipo()
    _mock_chamar(monkeypatch, "isto não é json")
    out = metadados.gerar_metadados(
        {"tema": "meu tema", "roteiro": "meu roteiro"}, tipo.config, tipo.assets_dir
    )
    assert out["titulo"] == "meu tema"  # fallback
    assert out["descricao"] == "meu roteiro"
    assert out["tags"] == []


def test_normaliza_tags_dedup_e_limite(make_tipo, monkeypatch):
    tipo = make_tipo(config_extra={"publicacao": {"metadados": {"estrategia_tags": "nicho", "max_tags": 2}}})
    _mock_chamar(
        monkeypatch,
        json.dumps({"titulo": "t", "descricao": "d", "tags": ["X", "x", "y", "z"]}),
    )
    out = metadados.gerar_metadados({"tema": "t", "roteiro": "r"}, tipo.config, tipo.assets_dir)
    assert out["tags"] == ["X", "y"]  # dedup case-insensitive + corta em 2


def test_titulo_cortado_em_100(make_tipo, monkeypatch):
    tipo = make_tipo()
    _mock_chamar(monkeypatch, json.dumps({"titulo": "A" * 200, "descricao": "d", "tags": []}))
    out = metadados.gerar_metadados({"tema": "t", "roteiro": "r"}, tipo.config, tipo.assets_dir)
    assert len(out["titulo"]) == metadados.TITULO_MAX


def test_usa_prompt_do_asset_quando_existe(make_tipo, monkeypatch):
    tipo = make_tipo()
    (tipo.assets_dir / "system_prompt_metadados.txt").write_text("PROMPT CUSTOM", encoding="utf-8")
    capturado = {}

    def _fake(system, user, config):
        capturado["system"] = system
        return json.dumps({"titulo": "t", "descricao": "d", "tags": []})

    monkeypatch.setattr("publicacao.metadados._chamar_api", _fake)
    metadados.gerar_metadados({"tema": "t", "roteiro": "r"}, tipo.config, tipo.assets_dir)
    assert capturado["system"] == "PROMPT CUSTOM"


# --- checkpoint (obter_metadados) ----------------------------------------


def test_obter_metadados_reaproveita_checkpoint(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo()
    registro.gravar(tmp_path, metadados={"titulo": "já feito", "descricao": "d", "tags": []})

    def _explode(*a, **k):
        raise AssertionError("não deveria chamar o Groq (checkpoint)")

    monkeypatch.setattr("publicacao.metadados._chamar_api", _explode)
    out = metadados.obter_metadados(tmp_path, tipo.config, tipo.assets_dir)
    assert out["titulo"] == "já feito"


def test_obter_metadados_gera_e_persiste(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo()
    (tmp_path / "sidecar.json").write_text(
        json.dumps({"tema": "tema x", "roteiro": "roteiro x"}), encoding="utf-8"
    )
    _mock_chamar(monkeypatch, json.dumps({"titulo": "Novo", "descricao": "D", "tags": ["k"]}))

    out = metadados.obter_metadados(tmp_path, tipo.config, tipo.assets_dir)
    assert out["titulo"] == "Novo"
    # persistido em publicacao.json para o próximo passe
    assert registro.ler(tmp_path)["metadados"]["titulo"] == "Novo"
