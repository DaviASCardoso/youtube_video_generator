import pytest

from scripts import execucoes
from scripts.execucoes import (
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
    import scripts.youtube as y

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

    import scripts.youtube as y

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

    import scripts.youtube as y

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

    def fake_gerar(tema, tipo, output_path):
        from pathlib import Path

        base = Path(output_path)
        base.mkdir(parents=True, exist_ok=True)
        (base / "roteiro.txt").write_text("roteiro", encoding="utf-8")
        video = base / "video_final.mp4"
        video.write_bytes(b"x")
        return video

    monkeypatch.setattr(execucoes, "gerar_video", fake_gerar)

    import scripts.youtube as y

    monkeypatch.setattr(y, "publicar_video", lambda *a, **k: "https://youtu.be/ZZZ")

    caminho = execucoes.executar_com_captura("meu tema", tipo)
    assert caminho.name == "video_final.mp4"

    reg = hist.listar(tipo.id)[0]
    assert reg["status"] == "concluido"
    assert reg["url_publicacao"] == "https://youtu.be/ZZZ"
