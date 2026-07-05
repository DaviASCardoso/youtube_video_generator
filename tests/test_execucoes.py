import pytest

from operacoes import execucoes
from operacoes.execucoes import (
    ExecucaoEmAndamentoError,
    HistoricoExecucoes,
    _TransmissorLog,
)


def _youtube_cfg(publicar):
    return {
        "youtube": {
            "categoria_id": "22",
            "visibilidade": "private",
            "tags": [],
            "descricao_base": "",
            "publicar": publicar,
        }
    }


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
    assert reg["url_publicacao"] is None
    assert "id" in reg


def test_registrar_publicacao(hist):
    reg = hist.iniciar("canal", "Canal X", "t")
    hist.registrar_publicacao(reg["id"], "https://youtu.be/ABC")
    assert hist.obter(reg["id"])["url_publicacao"] == "https://youtu.be/ABC"


def test_iniciar_inclui_publicacao_vazia(hist):
    reg = hist.iniciar("canal", "Canal X", "t")
    assert reg["publicacao"] == []


def test_registrar_publicacao_destino_upsert(hist):
    reg = hist.iniciar("canal", "Canal X", "t")
    hist.registrar_publicacao_destino(
        reg["id"], "youtube", {"id": "V1", "url": "https://youtu.be/V1", "quota": 1600, "status": "publicado"}
    )
    atual = hist.obter(reg["id"])
    assert len(atual["publicacao"]) == 1
    assert atual["publicacao"][0]["destino"] == "youtube"
    assert atual["url_publicacao"] == "https://youtu.be/V1"  # compat

    # regravar o mesmo destino faz upsert (não duplica)
    hist.registrar_publicacao_destino(reg["id"], "youtube", {"id": "V1", "status": "publicado", "quota": 1600})
    assert len(hist.obter(reg["id"])["publicacao"]) == 1


def test_publicacao_de_reconcilia(hist):
    reg = hist.iniciar("canal", "Canal X", "t")
    assert hist.publicacao_de(reg["id"], "youtube") is None
    hist.registrar_publicacao_destino(reg["id"], "youtube", {"id": "V9", "status": "publicado"})
    rec = hist.publicacao_de(reg["id"], "youtube")
    assert rec["id"] == "V9"  # já publicado -> caller não republica


def test_marcar_aguardando_publicacao(hist):
    reg = hist.iniciar("canal", "Canal X", "t")
    hist.marcar_aguardando_publicacao(reg["id"])
    atual = hist.obter(reg["id"])
    assert atual["status"] == "aguardando_publicacao"
    assert atual["finalizado_em"] is not None


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


# --- _publicar_se_configurado (hook de publicação) ---

def test_publicar_desligado_nao_chama_youtube(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo(config_extra=_youtube_cfg(publicar=False))
    import publicacao.youtube as y

    chamou = []
    monkeypatch.setattr(y, "publicar_video", lambda *a, **k: chamou.append(1))
    execucoes._publicar_se_configurado("id", "tema", tipo, tmp_path / "video_final.mp4")
    assert chamou == []


def test_publicar_ligado_publica_e_registra_url(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo(config_extra=_youtube_cfg(publicar=True))
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)
    reg = hist.iniciar(tipo.id, tipo.nome, "tema")

    video = tmp_path / "out" / "video_final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"x")
    (video.parent / "roteiro.txt").write_text("meu roteiro", encoding="utf-8")

    import publicacao.youtube as y

    capturado = {}

    def fake_publicar(vp, tema, tp, roteiro):
        capturado["roteiro"] = roteiro
        return "https://youtu.be/AAA"

    monkeypatch.setattr(y, "publicar_video", fake_publicar)

    execucoes._publicar_se_configurado(reg["id"], "tema", tipo, video)
    assert hist.obter(reg["id"])["url_publicacao"] == "https://youtu.be/AAA"
    assert capturado["roteiro"] == "meu roteiro"  # roteiro.txt entra na descrição


def test_publicar_falha_nao_derruba_execucao(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo(config_extra=_youtube_cfg(publicar=True))
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)
    reg = hist.iniciar(tipo.id, tipo.nome, "tema")

    video = tmp_path / "video_final.mp4"
    video.write_bytes(b"x")

    import publicacao.youtube as y

    def boom(*a, **k):
        raise RuntimeError("sem token")

    monkeypatch.setattr(y, "publicar_video", boom)

    # não deve levantar; a URL fica None (publicação falhou, vídeo ok)
    execucoes._publicar_se_configurado(reg["id"], "tema", tipo, video)
    assert hist.obter(reg["id"])["url_publicacao"] is None


def test_executar_com_captura_gera_publica_e_conclui(
    make_tipo, monkeypatch, tmp_path, sistema_temp
):
    """Fluxo completo: gerar_video (mockado) -> publicar (mockado) -> concluir."""
    sistema_temp._config["saida"]["pasta_base"] = str(tmp_path / "out")
    tipo = make_tipo(config_extra=_youtube_cfg(publicar=True))
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)

    def fake_gerar(tema, tipo, output_path, ledger=None):
        from pathlib import Path

        base = Path(output_path)
        base.mkdir(parents=True, exist_ok=True)
        (base / "roteiro.txt").write_text("roteiro", encoding="utf-8")
        if ledger is not None:
            ledger.registrar("roteiro", "groq", 0.0005)
        video = base / "video_final.mp4"
        video.write_bytes(b"x")
        return video

    monkeypatch.setattr(execucoes, "gerar_video", fake_gerar)

    import publicacao.youtube as y

    monkeypatch.setattr(y, "publicar_video", lambda *a, **k: "https://youtu.be/ZZZ")

    caminho = execucoes.executar_com_captura("meu tema", tipo)
    assert caminho.name == "video_final.mp4"

    reg = hist.listar(tipo.id)[0]
    assert reg["status"] == "concluido"
    assert reg["url_publicacao"] == "https://youtu.be/ZZZ"
    assert reg["custo_total"] == 0.0005  # ledger do run anotado no histórico
    assert reg["provedores"] == {"roteiro": "groq"}


def test_pasta_da_execucao_do_output_path():
    reg = {"output_path": "output/tipo/2026/video_final.mp4", "log_path": None}
    assert execucoes.pasta_da_execucao(reg).as_posix() == "output/tipo/2026"


def test_pasta_da_execucao_cai_no_log(tmp_path):
    reg = {"output_path": None, "log_path": "output/tipo/2026/execucao.log"}
    assert execucoes.pasta_da_execucao(reg).as_posix() == "output/tipo/2026"


def test_pasta_da_execucao_sem_nada():
    assert execucoes.pasta_da_execucao({"output_path": None, "log_path": None}) is None


def test_executar_reaproveita_pasta_dada(make_tipo, monkeypatch, tmp_path, sistema_temp):
    from pathlib import Path

    tipo = make_tipo(config_extra=_youtube_cfg(publicar=False))
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)

    recebido = {}

    def fake_gerar(tema, tipo, output_path, ledger=None):
        recebido["output_path"] = Path(output_path)
        Path(output_path).mkdir(parents=True, exist_ok=True)
        video = Path(output_path) / "video_final.mp4"
        video.write_bytes(b"x")
        return video

    monkeypatch.setattr(execucoes, "gerar_video", fake_gerar)
    pasta = tmp_path / "run_antigo"
    execucoes.executar_com_captura("tema", tipo, output_path=pasta)
    assert recebido["output_path"] == pasta  # reusou a pasta, não gerou timestamp


def test_iniciar_inclui_campos_de_custo(hist):
    reg = hist.iniciar("canal", "Canal X", "t")
    assert reg["custo_total"] is None
    assert reg["custos"] == []
    assert reg["provedores"] == {}


def test_registrar_custos_anota_ledger(hist):
    from geracao.custo import Ledger

    reg = hist.iniciar("canal", "Canal X", "t")
    led = Ledger()
    led.registrar("roteiro", "groq", 0.0005)
    led.registrar("visuais", "flux", 0.02)
    hist.registrar_custos(reg["id"], led)

    atualizado = hist.obter(reg["id"])
    assert abs(atualizado["custo_total"] - 0.0205) < 1e-9
    assert atualizado["provedores"]["visuais"] == "flux"
    assert len(atualizado["custos"]) == 2


def test_publicar_prefere_roteiro_do_sidecar(make_tipo, monkeypatch, tmp_path):
    from geracao import sidecar as sc

    tipo = make_tipo(config_extra=_youtube_cfg(publicar=True))
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)
    reg = hist.iniciar(tipo.id, tipo.nome, "tema")

    video = tmp_path / "out" / "video_final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"x")
    # sidecar e roteiro.txt divergem: o handoff deve usar o sidecar.
    sc.escrever(video.parent, {"roteiro": "roteiro do sidecar"})
    (video.parent / "roteiro.txt").write_text("roteiro antigo", encoding="utf-8")

    import publicacao.youtube as y

    capturado = {}
    monkeypatch.setattr(
        y, "publicar_video", lambda vp, tema, tp, roteiro: capturado.setdefault("r", roteiro) or "u"
    )
    execucoes._publicar_se_configurado(reg["id"], "tema", tipo, video)
    assert capturado["r"] == "roteiro do sidecar"
