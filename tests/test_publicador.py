import json

import pytest

from operacoes.execucoes import HistoricoExecucoes
from publicacao import publicador
from publicacao.destinos import base
from publicacao.quota import QuotaDiaria


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    """Histórico e cota isolados, metadados/thumbnail mockados, e um destino fake
    registrado no lugar do YouTube para dirigir a orquestração sem rede."""
    hist = HistoricoExecucoes(tmp_path / "h.json")
    import operacoes.execucoes as ex

    monkeypatch.setattr(ex, "historico", hist)
    monkeypatch.setattr(publicador.quota_diaria, "_caminho", tmp_path / "quota.json")
    monkeypatch.setattr("time.sleep", lambda s: None)  # o motor não dorme nos testes
    # metadados/thumbnail: evita Groq/FLUX; sidecar não precisa existir
    monkeypatch.setattr(
        publicador.metadados_mod, "obter_metadados",
        lambda pasta, config, assets, ledger=None: {"titulo": "T", "descricao": "D", "tags": []},
    )
    monkeypatch.setattr(
        publicador.thumbnail_mod, "obter_thumbnail",
        lambda pasta, config, assets, ledger=None: None,
    )
    return hist


class _DestinoFake:
    resultado = {"id": "V1", "url": "https://x/V1", "quota": 1600, "privacidade": "public"}
    credencial = {"status": "valido", "detalhe": ""}
    erro = None

    def publicar(self, video_path, metadados, thumb_path, opcoes, tipo):
        if type(self).erro:
            raise type(self).erro
        return type(self).resultado

    def checar_credencial(self, tipo):
        return type(self).credencial


@pytest.fixture
def destino_fake(monkeypatch):
    _DestinoFake.erro = None
    _DestinoFake.credencial = {"status": "valido", "detalhe": ""}
    monkeypatch.setattr(base, "obter", lambda nome: _DestinoFake())
    return _DestinoFake


def _tipo_publicando(make_tipo, revisao="auto"):
    return make_tipo(
        config_extra={
            "publicacao": {"revisao": revisao, "destinos": {"youtube": {"ativo": True}}}
        }
    )


def _run(hist, tipo, pasta):
    reg = hist.iniciar(tipo.id, tipo.nome, "tema")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "video_final.mp4").write_bytes(b"x")
    return reg


def test_sem_destino_ativo_nao_publica(make_tipo, ambiente, tmp_path):
    tipo = make_tipo()  # nenhum destino ativo
    reg = _run(ambiente, tipo, tmp_path / "run")
    assert publicador.publicar(tipo, tmp_path / "run", reg["id"]) == "sem_destino"
    assert ambiente.obter(reg["id"])["publicacao"] == []


# --- gate de conformidade na publicação -------------------------------------


def test_conformidade_bloqueia_publicacao(make_tipo, ambiente, destino_fake, tmp_path, monkeypatch):
    from conformidade.parecer import Parecer

    monkeypatch.setattr(
        publicador, "_avaliar_conformidade",
        lambda tipo, pasta, cfg, eid: Parecer(bloqueado=True, motivos_bloqueio=["disclosure exigido mas desativado"]),
    )
    tipo = _tipo_publicando(make_tipo)
    reg = _run(ambiente, tipo, tmp_path / "run")

    assert publicador.publicar(tipo, tmp_path / "run", reg["id"]) == "bloqueado_conformidade"
    atual = ambiente.obter(reg["id"])
    assert atual["status"] == "bloqueado_conformidade"
    assert atual["publicacao"] == []  # nada subiu
    assert "disclosure" in atual["erro"]


def test_conformidade_flag_forca_revisao(make_tipo, ambiente, destino_fake, tmp_path, monkeypatch):
    from conformidade.parecer import Parecer

    monkeypatch.setattr(
        publicador, "_avaliar_conformidade",
        lambda tipo, pasta, cfg, eid: Parecer(flags=["autenticidade: sameness alto (90)"]),
    )
    tipo = _tipo_publicando(make_tipo, revisao="auto")  # auto, mas o flag força revisão
    reg = _run(ambiente, tipo, tmp_path / "run")

    assert publicador.publicar(tipo, tmp_path / "run", reg["id"]) == "aguardando_revisao"
    atual = ambiente.obter(reg["id"])
    assert atual["status"] == "aguardando_publicacao"
    assert atual["publicacao"] == []


def test_conformidade_aprovado_reaplica_bloqueio(make_tipo, ambiente, destino_fake, tmp_path, monkeypatch):
    from conformidade.parecer import Parecer

    monkeypatch.setattr(
        publicador, "_avaliar_conformidade",
        lambda tipo, pasta, cfg, eid: Parecer(bloqueado=True, motivos_bloqueio=["ativo sem licença: trilha:musica"]),
    )
    tipo = _tipo_publicando(make_tipo)
    reg = _run(ambiente, tipo, tmp_path / "run")
    ambiente.definir_log_path(reg["id"], tmp_path / "run" / "execucao.log")

    # o Aprovar & publicar (que pula o publicar()) também barra
    assert publicador.publicar_aprovado(reg["id"]) == "bloqueado_conformidade"
    assert ambiente.obter(reg["id"])["status"] == "bloqueado_conformidade"
    assert ambiente.obter(reg["id"])["publicacao"] == []


def test_auto_publica_e_registra(make_tipo, ambiente, destino_fake, tmp_path):
    tipo = _tipo_publicando(make_tipo)
    reg = _run(ambiente, tipo, tmp_path / "run")
    assert publicador.publicar(tipo, tmp_path / "run", reg["id"]) == "publicado"
    rec = ambiente.publicacao_de(reg["id"], "youtube")
    assert rec["id"] == "V1" and rec["status"] == "publicado"


def test_revisar_segura_e_marca_aguardando(make_tipo, ambiente, destino_fake, tmp_path):
    tipo = _tipo_publicando(make_tipo, revisao="revisar")
    reg = _run(ambiente, tipo, tmp_path / "run")
    assert publicador.publicar(tipo, tmp_path / "run", reg["id"]) == "aguardando_revisao"
    atual = ambiente.obter(reg["id"])
    assert atual["status"] == "aguardando_publicacao"
    assert atual["publicacao"] == []  # nada subiu ainda


def test_idempotencia_nao_republica(make_tipo, ambiente, destino_fake, tmp_path):
    tipo = _tipo_publicando(make_tipo)
    reg = _run(ambiente, tipo, tmp_path / "run")
    ambiente.registrar_publicacao_destino(reg["id"], "youtube", {"id": "JA", "url": "u", "status": "publicado"})
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    # continua com o id antigo (não reenviou)
    assert ambiente.publicacao_de(reg["id"], "youtube")["id"] == "JA"


def test_credencial_expirada_pula(make_tipo, ambiente, destino_fake, tmp_path):
    destino_fake.credencial = {"status": "expirado", "detalhe": "token morto"}
    tipo = _tipo_publicando(make_tipo)
    reg = _run(ambiente, tipo, tmp_path / "run")
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    rec = ambiente.publicacao_de(reg["id"], "youtube")
    assert rec["status"] == "credencial_expirado" and "id" not in rec


def test_cota_atingida_adia(make_tipo, ambiente, destino_fake, tmp_path, monkeypatch):
    tipo = _tipo_publicando(make_tipo)
    # cap_diario default 5; simula 5 uploads hoje para essa credencial
    q = QuotaDiaria(tmp_path / "quota.json")
    monkeypatch.setattr(publicador, "quota_diaria", q)
    for _ in range(5):
        q.registrar(f"youtube:{tipo.id}")
    reg = _run(ambiente, tipo, tmp_path / "run")
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    assert ambiente.publicacao_de(reg["id"], "youtube")["status"] == "adiado_cota"


def test_destino_falho_degrada(make_tipo, ambiente, destino_fake, tmp_path):
    destino_fake.erro = RuntimeError("upload caiu")
    tipo = _tipo_publicando(make_tipo)
    reg = _run(ambiente, tipo, tmp_path / "run")
    # não levanta; o motor retenta (transitório) e, esgotado, registra dead-letter
    # neste destino — os demais seguiriam e o run não quebra.
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    rec = ambiente.publicacao_de(reg["id"], "youtube")
    assert rec["status"] == "dead_letter"
    assert "upload caiu" in rec["erro"]


def test_destino_cota_no_upload_adia(make_tipo, ambiente, destino_fake, tmp_path):
    """Um 429 de quota durante o upload é classificado como quota → o destino é adiado
    (não vira dead-letter)."""

    class _ErroQuota(Exception):
        status_code = 429

        def __str__(self):
            return "quota exceeded"

    destino_fake.erro = _ErroQuota()
    tipo = _tipo_publicando(make_tipo)
    reg = _run(ambiente, tipo, tmp_path / "run")
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    assert ambiente.publicacao_de(reg["id"], "youtube")["status"] == "adiado_cota"


def test_agendado_seta_publish_at(make_tipo, ambiente, tmp_path, monkeypatch):
    tipo = make_tipo(
        config_extra={
            "publicacao": {
                "destinos": {"youtube": {"ativo": True}},
                "timing": {"modo": "agendado", "horario": "18:00", "fuso_horario": "America/Sao_Paulo"},
            }
        }
    )
    capturado = {}

    class _D:
        def checar_credencial(self, tipo):
            return {"status": "valido", "detalhe": ""}

        def publicar(self, video_path, metadados, thumb_path, opcoes, tipo):
            capturado["publish_at"] = opcoes["publish_at"]
            return {"id": "V", "url": "u", "quota": 1600, "privacidade": "private", "agendado_para": opcoes["publish_at"]}

    monkeypatch.setattr(base, "obter", lambda nome: _D())
    reg = _run(ambiente, tipo, tmp_path / "run")
    publicador.publicar(tipo, tmp_path / "run", reg["id"])
    assert capturado["publish_at"] and capturado["publish_at"].endswith("Z")
    assert ambiente.publicacao_de(reg["id"], "youtube")["status"] == "agendado"
