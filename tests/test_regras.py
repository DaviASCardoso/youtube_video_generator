from conformidade.regras import (
    REGRAS_PADRAO,
    RegrasConformidade,
    regras_de,
)


def _store(tmp_path):
    return RegrasConformidade(tmp_path / "conformidade" / "regras.json")


def test_estado_inicial_sem_arquivo(tmp_path):
    r = _store(tmp_path)
    est = r.estado()
    assert est["versao"] == 0
    assert est["atualizado_em"] is None
    assert est["changelog"] == []
    assert est["regras"] == REGRAS_PADRAO
    # atual() devolve os defaults
    assert r.atual() == REGRAS_PADRAO


def test_atual_e_independente_do_padrao(tmp_path):
    r = _store(tmp_path)
    r.atual()["marca"]["bloqueio"].append("mutado")
    assert "mutado" not in REGRAS_PADRAO["marca"]["bloqueio"]


def test_publicar_sobe_versao_e_registra_changelog(tmp_path):
    r = _store(tmp_path)
    novas = {"disclosure": {}, "marca": {"bloqueio": ["x"], "sensivel": []}, "licencas": {"flux": True}}

    est1 = r.publicar(novas, nota="endurecer brand safety")
    assert est1["versao"] == 1
    assert est1["atualizado_em"] is not None
    assert est1["regras"] == novas
    assert est1["changelog"][-1]["nota"] == "endurecer brand safety"

    est2 = r.publicar({"disclosure": {}, "marca": {"bloqueio": [], "sensivel": []}, "licencas": {}}, nota="v2")
    assert est2["versao"] == 2
    assert [c["versao"] for c in est2["changelog"]] == [1, 2]


def test_changelog_mais_recente_primeiro(tmp_path):
    r = _store(tmp_path)
    r.publicar(REGRAS_PADRAO, nota="a")
    r.publicar(REGRAS_PADRAO, nota="b")
    cl = r.changelog()
    assert [c["nota"] for c in cl] == ["b", "a"]


def test_persistido_entre_instancias(tmp_path):
    caminho = tmp_path / "conformidade" / "regras.json"
    RegrasConformidade(caminho).publicar(REGRAS_PADRAO, nota="inicial")
    # uma nova instância enxerga a versão gravada
    assert RegrasConformidade(caminho).versao() == 1


def test_arquivo_corrompido_cai_no_default(tmp_path):
    caminho = tmp_path / "conformidade" / "regras.json"
    caminho.parent.mkdir(parents=True)
    caminho.write_text("{ não é json", encoding="utf-8")
    r = RegrasConformidade(caminho)
    assert r.atual() == REGRAS_PADRAO
    assert r.versao() == 0


def test_regras_de_usa_pasta_do_tipo(make_tipo):
    tipo = make_tipo()
    r = regras_de(tipo)
    r.publicar(REGRAS_PADRAO, nota="x")
    assert (tipo.caminho / "conformidade" / "regras.json").exists()
    assert regras_de(tipo).versao() == 1
