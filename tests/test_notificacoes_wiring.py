"""Prova que os pontos-fonte chamam notificacoes.emitir com a categoria certa
(com emitir mockado — sem rede), e que o caminho de sucesso default NÃO notifica."""

import pytest

from operacoes import execucoes
from operacoes import notificacoes
from operacoes.execucoes import HistoricoExecucoes
from publicacao import publicador
from publicacao.destinos import base
from publicacao.quota import QuotaDiaria
from descoberta import descoberta as orq
from descoberta.candidato import Candidato, agora


@pytest.fixture
def emissoes(monkeypatch):
    """Captura as categorias emitidas em vez de fazer POST ntfy."""
    reg = []
    monkeypatch.setattr(
        notificacoes, "emitir",
        lambda cat, titulo, msg, prioridade=None: reg.append(cat) or True,
    )
    return reg


# --- Operações: run falhou ---------------------------------------------------


def test_run_falhou_emite(make_tipo, monkeypatch, tmp_path, sistema_temp, emissoes):
    sistema_temp._config["saida"]["pasta_base"] = str(tmp_path / "out")
    tipo = make_tipo()
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)

    def _boom(tema, tipo, output_path, ledger=None):
        from pathlib import Path

        Path(output_path).mkdir(parents=True, exist_ok=True)
        raise RuntimeError("estourou")

    monkeypatch.setattr(execucoes, "gerar_video", _boom)

    with pytest.raises(RuntimeError):
        execucoes.executar_com_captura("meu tema", tipo)
    assert "run_falhou" in emissoes


def test_run_ok_nao_emite(make_tipo, monkeypatch, tmp_path, sistema_temp, emissoes):
    sistema_temp._config["saida"]["pasta_base"] = str(tmp_path / "out")
    tipo = make_tipo()  # sem destino ativo (default)
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)

    def _ok(tema, tipo, output_path, ledger=None):
        from pathlib import Path

        base_dir = Path(output_path)
        base_dir.mkdir(parents=True, exist_ok=True)
        video = base_dir / "video_final.mp4"
        video.write_bytes(b"x")
        return video

    monkeypatch.setattr(execucoes, "gerar_video", _ok)
    execucoes.executar_com_captura("meu tema", tipo)
    assert emissoes == []  # caminho de sucesso default é silencioso


# --- Publicação: cota / credencial / revisão --------------------------------


class _Destino:
    def __init__(self, cred):
        self._cred = cred

    def checar_credencial(self, tipo):
        return self._cred

    def publicar(self, video_path, metadados, thumb_path, opcoes, tipo):
        return {"id": "V", "url": "u", "quota": 1600, "privacidade": "public"}


def _ambiente_pub(monkeypatch, tmp_path, cred=None):
    hist = HistoricoExecucoes(tmp_path / "h.json")
    monkeypatch.setattr(execucoes, "historico", hist)
    monkeypatch.setattr(publicador.quota_diaria, "_caminho", tmp_path / "quota.json")
    monkeypatch.setattr(
        publicador.metadados_mod, "obter_metadados",
        lambda *a, **k: {"titulo": "T", "descricao": "D", "tags": []},
    )
    monkeypatch.setattr(publicador.thumbnail_mod, "obter_thumbnail", lambda *a, **k: None)
    cred = cred or {"status": "valido", "detalhe": ""}
    monkeypatch.setattr(base, "obter", lambda nome: _Destino(cred))
    return hist


def _tipo_pub(make_tipo, revisao="auto"):
    return make_tipo(
        config_extra={"publicacao": {"revisao": revisao, "destinos": {"youtube": {"ativo": True}}}}
    )


def _run(hist, tipo, pasta):
    reg = hist.iniciar(tipo.id, tipo.nome, "tema")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "video_final.mp4").write_bytes(b"x")
    return reg


def test_credencial_expirando_emite(make_tipo, monkeypatch, tmp_path, emissoes):
    hist = _ambiente_pub(monkeypatch, tmp_path, cred={"status": "expirando", "detalhe": "3 dias"})
    tipo = _tipo_pub(make_tipo)
    reg = _run(hist, tipo, tmp_path / "run")
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    assert "credencial" in emissoes


def test_cota_atingida_emite(make_tipo, monkeypatch, tmp_path, emissoes):
    hist = _ambiente_pub(monkeypatch, tmp_path)
    q = QuotaDiaria(tmp_path / "quota.json")
    monkeypatch.setattr(publicador, "quota_diaria", q)
    tipo = _tipo_pub(make_tipo)
    for _ in range(5):  # cap default 5
        q.registrar(f"youtube:{tipo.id}")
    reg = _run(hist, tipo, tmp_path / "run")
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    assert "cota_atingida" in emissoes


def test_revisao_publicacao_emite(make_tipo, monkeypatch, tmp_path, emissoes):
    hist = _ambiente_pub(monkeypatch, tmp_path)
    tipo = _tipo_pub(make_tipo, revisao="revisar")
    reg = _run(hist, tipo, tmp_path / "run")
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    assert "revisao_pendente" in emissoes


def test_publicacao_auto_ok_nao_emite(make_tipo, monkeypatch, tmp_path, emissoes):
    hist = _ambiente_pub(monkeypatch, tmp_path)
    tipo = _tipo_pub(make_tipo)  # auto, credencial válida, cota livre
    reg = _run(hist, tipo, tmp_path / "run")
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    assert emissoes == []


# --- Descoberta: tema pendente ----------------------------------------------


def _c(texto, forca=0.5):
    return Candidato(texto=texto, fonte="reddit", forca_sinal=forca, observado_em=agora(), categoria="trending")


def test_descoberta_pendente_emite(make_tipo, monkeypatch, emissoes):
    monkeypatch.setattr(orq.dedup, "sinais_recentes", lambda tipo, dias: set())

    class _HistFake:
        def registrar(self, *a, **k):
            return None

    monkeypatch.setattr(orq, "historico_tendencias", _HistFake())
    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([_c("A")], {}))

    def _av(c, tipo, cfg):
        c.fit_score = 80.0
        c.tema = c.texto
        return True

    monkeypatch.setattr(orq.fit, "avaliar", _av)

    tipo = make_tipo(config_extra={"descoberta": {"modo_revisao": "revisar"}})
    orq.decidir_tema(tipo)
    assert "revisao_pendente" in emissoes


def test_descoberta_auto_nao_emite(make_tipo, monkeypatch, emissoes):
    monkeypatch.setattr(orq.dedup, "sinais_recentes", lambda tipo, dias: set())

    class _HistFake:
        def registrar(self, *a, **k):
            return None

    monkeypatch.setattr(orq, "historico_tendencias", _HistFake())
    monkeypatch.setattr(orq, "_coletar", lambda t, c: ([_c("A")], {}))

    def _av(c, tipo, cfg):
        c.fit_score = 80.0
        c.tema = c.texto
        return True

    monkeypatch.setattr(orq.fit, "avaliar", _av)

    tipo = make_tipo()  # modo_revisao auto (default)
    orq.decidir_tema(tipo)
    assert emissoes == []
