import operacoes.execucoes as execucoes
from operacoes import recuperacao
from operacoes.execucoes import HistoricoExecucoes


def _hist(monkeypatch, tmp_path):
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)
    return hist


def test_recupera_apenas_orfaos_executando(monkeypatch, tmp_path):
    hist = _hist(monkeypatch, tmp_path)
    orfao = hist.iniciar("canal", "Canal", "tema órfão")
    hist.definir_log_path(orfao["id"], tmp_path / "run_orfao" / "execucao.log")
    # outro tipo, já concluído: não deve ser recuperado
    concluido = hist.iniciar("outro", "Outro", "tema ok")
    hist.concluir(concluido["id"], tmp_path / "run_ok" / "video_final.mp4")

    chamadas = []
    recuperados = recuperacao.recuperar_execucoes(
        lambda tid, tema, ex, out: chamadas.append((tid, tema, ex["id"], out))
    )

    # só o órfão 'executando' é re-enfileirado
    assert [r["id"] for r in recuperados] == [orfao["id"]]
    assert len(chamadas) == 1
    tid, tema, eid, out = chamadas[0]
    assert tid == "canal"
    assert tema == "tema órfão"
    assert eid == orfao["id"]
    # reusa a pasta do run (pai do log)
    assert out.replace("\\", "/").endswith("run_orfao")


def test_marca_recuperado(monkeypatch, tmp_path):
    hist = _hist(monkeypatch, tmp_path)
    orfao = hist.iniciar("canal", "Canal", "t")

    recuperacao.recuperar_execucoes(lambda *a: None)

    reg = hist.obter(orfao["id"])
    assert reg["recuperado"] is True
    assert reg["status"] == "executando"  # ainda em execução (será concluído ao retomar)


def test_reusa_o_registro_orfao_sem_novo_iniciar(monkeypatch, tmp_path):
    hist = _hist(monkeypatch, tmp_path)
    orfao = hist.iniciar("canal", "Canal", "t")

    recuperados = recuperacao.recuperar_execucoes(lambda *a: None)

    # nenhum registro novo foi criado — reusa o órfão (respeita um-run-por-tipo)
    assert len(hist.listar()) == 1
    assert recuperados[0]["id"] == orfao["id"]


def test_start_limpo_nao_recupera_nada(monkeypatch, tmp_path):
    _hist(monkeypatch, tmp_path)
    chamadas = []
    recuperados = recuperacao.recuperar_execucoes(lambda *a: chamadas.append(a))
    assert recuperados == []
    assert chamadas == []
