from geracao import sidecar
from geracao.custo import Ledger


def test_montar_resume_o_run():
    led = Ledger()
    led.registrar("roteiro", "groq", 0.0005)
    led.registrar("visuais", "flux", 0.02)
    frases = [(1, "primeira"), (2, "segunda")]

    sc = sidecar.montar("meu tema", frases, duracao_seg=12.3456, ledger=led)

    assert sc["tema"] == "meu tema"
    assert sc["roteiro"] == "primeira\nsegunda"
    assert sc["n_cenas"] == 2
    assert sc["duracao_seg"] == 12.346
    assert abs(sc["custo_total_usd"] - 0.0205) < 1e-9
    assert sc["provedores"]["visuais"] == "flux"
    assert "gerado_em" in sc


def test_escrever_e_ler_roundtrip(tmp_path):
    dados = {"tema": "x", "n_cenas": 1}
    caminho = sidecar.escrever(tmp_path, dados)
    assert caminho.name == sidecar.NOME_ARQUIVO
    assert sidecar.ler(tmp_path) == dados


def test_ler_ausente(tmp_path):
    assert sidecar.ler(tmp_path) is None


def test_ler_corrompido(tmp_path):
    (tmp_path / sidecar.NOME_ARQUIVO).write_text("{ nao é json", encoding="utf-8")
    assert sidecar.ler(tmp_path) is None
