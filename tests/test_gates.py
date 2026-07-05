import pytest

from geracao import gates
from geracao.configuracao import GERACAO_PADRAO
from geracao.gates import GateReprovado


def test_validar_roteiro_ok():
    frases = [(1, "Uma frase inteira aqui."), (2, "Outra frase completa.")]
    gates.validar_roteiro(frases, GERACAO_PADRAO)  # não levanta


def test_validar_roteiro_vazio():
    with pytest.raises(GateReprovado):
        gates.validar_roteiro([], GERACAO_PADRAO)


def test_validar_roteiro_frase_vazia():
    with pytest.raises(GateReprovado):
        gates.validar_roteiro([(1, "ok"), (2, "   ")], GERACAO_PADRAO)


def test_validar_roteiro_bounds_de_tamanho():
    cfg = {"roteiro": {"min_palavras": 5, "max_palavras": 10}}
    with pytest.raises(GateReprovado):
        gates.validar_roteiro([(1, "curto demais")], cfg)  # 2 palavras < 5
    with pytest.raises(GateReprovado):
        gates.validar_roteiro([(1, "uma duas tres quatro cinco seis sete oito nove dez onze")], cfg)


def test_validar_roteiro_default_permissivo():
    # min_palavras=1 padrão: uma frase curtinha passa
    gates.validar_roteiro([(1, "frase um")], GERACAO_PADRAO)


def test_validar_plano_visual_ok():
    gates.validar_plano_visual([(1, "a"), (2, "b")], ["p1", "p2"])


def test_validar_plano_visual_desalinhado():
    with pytest.raises(GateReprovado):
        gates.validar_plano_visual([(1, "a"), (2, "b")], ["p1"])


def test_validar_narracao_ok(tmp_path):
    audio = tmp_path / "frase_1.mp3"
    audio.write_bytes(b"0" * 1000)
    gates.validar_narracao(audio)


def test_validar_narracao_silenciosa(tmp_path):
    audio = tmp_path / "frase_1.mp3"
    audio.write_bytes(b"0" * 10)  # abaixo do mínimo
    with pytest.raises(GateReprovado):
        gates.validar_narracao(audio)


def test_validar_narracao_ausente(tmp_path):
    with pytest.raises(GateReprovado):
        gates.validar_narracao(tmp_path / "nao_existe.mp3")


def test_validar_visuais_ok(tmp_path):
    imgs = []
    for i in (1, 2):
        p = tmp_path / f"imagem_{i}.png"
        p.write_bytes(b"x")
        imgs.append(p)
    gates.validar_visuais(imgs, esperado=2)


def test_validar_visuais_contagem_errada(tmp_path):
    p = tmp_path / "imagem_1.png"
    p.write_bytes(b"x")
    with pytest.raises(GateReprovado):
        gates.validar_visuais([p], esperado=2)


def test_validar_visuais_imagem_vazia(tmp_path):
    p = tmp_path / "imagem_1.png"
    p.write_bytes(b"")
    with pytest.raises(GateReprovado):
        gates.validar_visuais([p], esperado=1)
