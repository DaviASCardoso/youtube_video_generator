from publicacao import registro


def test_ler_ausente(tmp_path):
    assert registro.ler(tmp_path) == {}


def test_gravar_e_ler(tmp_path):
    registro.gravar(tmp_path, metadados={"titulo": "t"})
    assert registro.ler(tmp_path)["metadados"]["titulo"] == "t"


def test_gravar_faz_merge_por_chave(tmp_path):
    registro.gravar(tmp_path, metadados={"titulo": "t"})
    registro.gravar(tmp_path, thumbnail={"texto": "OI"})
    dados = registro.ler(tmp_path)
    assert dados["metadados"]["titulo"] == "t"  # preservado
    assert dados["thumbnail"]["texto"] == "OI"


def test_ler_corrompido(tmp_path):
    (tmp_path / registro.NOME_ARQUIVO).write_text("{ não é json", encoding="utf-8")
    assert registro.ler(tmp_path) == {}
