import pytest

from scripts.execucoes import (
    ExecucaoEmAndamentoError,
    HistoricoExecucoes,
    _TransmissorLog,
)


@pytest.fixture
def hist(tmp_path):
    return HistoricoExecucoes(tmp_path / "historico.json")


def test_iniciar_cria_registro(hist):
    reg = hist.iniciar("canal", "Canal X", "um tema")
    assert reg["tipo_id"] == "canal"
    assert reg["tipo_nome"] == "Canal X"
    assert reg["tema"] == "um tema"
    assert reg["status"] == "executando"
    assert reg["finalizado_em"] is None
    assert "id" in reg


def test_em_execucao(hist):
    assert hist.em_execucao("canal") is False
    hist.iniciar("canal", "Canal X", "t")
    assert hist.em_execucao("canal") is True


def test_iniciar_duplicado_levanta(hist):
    hist.iniciar("canal", "Canal X", "t1")
    with pytest.raises(ExecucaoEmAndamentoError):
        hist.iniciar("canal", "Canal X", "t2")


def test_concluir_libera_novo_inicio(hist):
    reg = hist.iniciar("canal", "Canal X", "t1")
    hist.concluir(reg["id"], "output/video.mp4")
    atualizado = hist.obter(reg["id"])
    assert atualizado["status"] == "concluido"
    assert atualizado["output_path"] == "output/video.mp4"
    assert atualizado["finalizado_em"] is not None
    # com a anterior concluída, uma nova execução pode começar
    hist.iniciar("canal", "Canal X", "t2")


def test_falhar_registra_erro(hist):
    reg = hist.iniciar("canal", "Canal X", "t")
    hist.falhar(reg["id"], "estourou")
    atualizado = hist.obter(reg["id"])
    assert atualizado["status"] == "erro"
    assert atualizado["erro"] == "estourou"


def test_listar_filtra_por_tipo(hist):
    hist.iniciar("a", "A", "t")
    r = hist.iniciar("b", "B", "t")
    hist.concluir(r["id"], "x")
    assert len(hist.listar()) == 2
    assert [e["tipo_id"] for e in hist.listar("a")] == ["a"]


def test_obter_inexistente_levanta(hist):
    with pytest.raises(KeyError):
        hist.obter("nao_existe")


def test_migrar_tipo_id_mantem_nome(hist):
    reg = hist.iniciar("antigo", "Nome Antigo", "t")
    hist.migrar_tipo_id("antigo", "novo")
    atualizado = hist.obter(reg["id"])
    assert atualizado["tipo_id"] == "novo"
    assert atualizado["tipo_nome"] == "Nome Antigo"  # rótulo congelado


def test_transmissor_publica_para_assinante():
    t = _TransmissorLog()
    fila = t.assinar("ex1")
    t.registrar_linha("ex1", "linha 1")
    assert fila.get_nowait() == "linha 1"


def test_transmissor_encerrar_envia_sentinela():
    t = _TransmissorLog()
    fila = t.assinar("ex1")
    t.encerrar("ex1")
    assert fila.get_nowait() is None


def test_transmissor_linhas_ate_agora():
    t = _TransmissorLog()
    t.registrar_linha("ex1", "a")
    t.registrar_linha("ex1", "b")
    assert t.linhas_ate_agora("ex1") == ["a", "b"]


def test_transmissor_desassinar_para_de_receber():
    t = _TransmissorLog()
    fila = t.assinar("ex1")
    t.desassinar("ex1", fila)
    t.registrar_linha("ex1", "linha")
    assert fila.empty()
