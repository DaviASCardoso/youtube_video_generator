from geracao import checkpoint


def test_artefato_valido_arquivo_ok(tmp_path):
    f = tmp_path / "roteiro.txt"
    f.write_text("conteudo", encoding="utf-8")
    assert checkpoint.artefato_valido(f)


def test_artefato_valido_arquivo_vazio(tmp_path):
    f = tmp_path / "vazio.txt"
    f.write_text("", encoding="utf-8")
    assert not checkpoint.artefato_valido(f)


def test_artefato_valido_ausente(tmp_path):
    assert not checkpoint.artefato_valido(tmp_path / "nao_existe.txt")


def test_artefato_valido_com_validador(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("abc", encoding="utf-8")
    assert checkpoint.artefato_valido(f, validar=lambda p: p.read_text() == "abc")
    assert not checkpoint.artefato_valido(f, validar=lambda p: p.read_text() == "xyz")


def test_todos_validos(tmp_path):
    a = tmp_path / "1.png"
    b = tmp_path / "2.png"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    assert checkpoint.todos_validos([a, b])
    assert not checkpoint.todos_validos([a, tmp_path / "faltando.png"])
    assert not checkpoint.todos_validos([])  # lista vazia


def test_deve_reaproveitar_respeita_toggle(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert checkpoint.deve_reaproveitar(f, reaproveitar=True)
    assert not checkpoint.deve_reaproveitar(f, reaproveitar=False)  # desligado
