import conformidade.conformidade as conf
from conformidade.auditoria import auditoria_de
from conformidade.configuracao import mesclar_conformidade
from geracao import sidecar as sidecar_mod


def _tipo_ativo(make_tipo, extra=None):
    cfg = {"ativo": True}
    if extra:
        cfg.update(extra)
    return make_tipo(config_extra={"conformidade": cfg})


def _sidecar(pasta, provedores=None, custos=None, roteiro="um roteiro", tema="um tema"):
    pasta.mkdir(parents=True, exist_ok=True)
    dados = {
        "tema": tema,
        "roteiro": roteiro,
        "provedores": provedores or {"narracao": "google", "visuais": "pexels", "roteiro": "groq"},
    }
    if custos is not None:
        dados["custos"] = custos
    return sidecar_mod.escrever(pasta, dados)


# --- modo_efetivo ------------------------------------------------------------


def test_modo_efetivo_estrategia_modula():
    cfg = mesclar_conformidade({"estrategia": "equilibrada"})
    assert conf.modo_efetivo("marca", cfg) == "equilibrada"  # inalterado
    assert conf.modo_efetivo("autenticidade", cfg) == "advisory"

    estrita = mesclar_conformidade({"estrategia": "estrita"})
    assert conf.modo_efetivo("autenticidade", estrita) == "equilibrada"  # +1
    assert conf.modo_efetivo("marca", estrita) == "bloquear"

    permissiva = mesclar_conformidade({"estrategia": "permissiva"})
    assert conf.modo_efetivo("marca", permissiva) == "advisory"  # -1
    assert conf.modo_efetivo("disclosure", permissiva) == "equilibrada"


# --- avaliar_tema ------------------------------------------------------------


def test_avaliar_tema_inerte_quando_desligado(make_tipo):
    tipo = make_tipo()  # conformidade.ativo = False (default)
    v = conf.avaliar_tema(tipo, "como lidar com suicídio")
    assert v.resultado == "liberado"  # inerte: não veta mesmo com termo de bloqueio
    assert auditoria_de(tipo).listar() == []  # e não audita


def test_avaliar_tema_bloqueia_e_audita(make_tipo, monkeypatch):
    monkeypatch.setattr(conf.mrc, "_chamar_api", lambda s, u, c: '{"apropriado": true}')
    tipo = _tipo_ativo(make_tipo)
    v = conf.avaliar_tema(tipo, "um relato de tortura detalhado")
    assert v.bloqueado is True
    audit = auditoria_de(tipo).listar()
    assert len(audit) == 1
    assert audit[0]["etapa"] == "descoberta" and audit[0]["resultado"] == "bloqueado"


def test_avaliar_tema_flag_limitrofe(make_tipo, monkeypatch):
    monkeypatch.setattr(conf.mrc, "_chamar_api", lambda s, u, c: '{"apropriado": true}')
    tipo = _tipo_ativo(make_tipo)
    v = conf.avaliar_tema(tipo, "lidando com a morte de um ente querido")
    assert v.sinalizado is True


# --- avaliar_publicacao ------------------------------------------------------


def test_publicacao_inerte_quando_desligado(make_tipo, tmp_path):
    tipo = make_tipo()
    _sidecar(tmp_path / "run")
    parecer = conf.avaliar_publicacao(tipo, tmp_path / "run", {"visibilidade": {"disclosure_sintetico": True}})
    assert parecer.bloqueado is False and parecer.flags == []
    assert auditoria_de(tipo).listar() == []


def test_disclosure_exigido_e_ligado_passa(make_tipo, tmp_path, monkeypatch):
    monkeypatch.setattr(conf, "_roteiros_recentes", lambda *a: [])
    tipo = _tipo_ativo(make_tipo)
    _sidecar(tmp_path / "run")  # google + pexels → disclosure exigido
    parecer = conf.avaliar_publicacao(
        tipo, tmp_path / "run", {"visibilidade": {"disclosure_sintetico": True}}, execucao_id="E1"
    )
    assert parecer.disclosure_requer is True
    assert parecer.bloqueado is False
    audit = auditoria_de(tipo).de_execucao("E1")
    assert audit and audit[0]["disclosure"]["requer"] is True


def test_disclosure_exigido_mas_desligado_bloqueia(make_tipo, tmp_path, monkeypatch):
    monkeypatch.setattr(conf, "_roteiros_recentes", lambda *a: [])
    tipo = _tipo_ativo(make_tipo)
    _sidecar(tmp_path / "run")
    parecer = conf.avaliar_publicacao(
        tipo, tmp_path / "run", {"visibilidade": {"disclosure_sintetico": False}}
    )
    assert parecer.bloqueado is True
    assert any("disclosure" in m for m in parecer.motivos_bloqueio)


def test_licenca_ausente_bloqueia(make_tipo, tmp_path, monkeypatch):
    monkeypatch.setattr(conf, "_roteiros_recentes", lambda *a: [])
    tipo = _tipo_ativo(make_tipo)
    _sidecar(
        tmp_path / "run",
        provedores={"narracao": "google", "visuais": "pexels"},
        custos=[{"estagio": "trilha", "provedor": "musica_pirata"}],
    )
    parecer = conf.avaliar_publicacao(
        tipo, tmp_path / "run", {"visibilidade": {"disclosure_sintetico": True}}
    )
    assert parecer.bloqueado is True
    assert any("licença" in m for m in parecer.motivos_bloqueio)


def test_autenticidade_flag_e_advisory(make_tipo, tmp_path, monkeypatch):
    monkeypatch.setattr(conf, "_roteiros_recentes", lambda *a: ["antigo 1"])
    monkeypatch.setattr(conf.aut, "_chamar_api", lambda s, u, c: '{"sameness": 95, "motivo": "igual"}')
    tipo = _tipo_ativo(make_tipo)
    _sidecar(tmp_path / "run")
    parecer = conf.avaliar_publicacao(
        tipo, tmp_path / "run", {"visibilidade": {"disclosure_sintetico": True}}
    )
    assert parecer.bloqueado is False  # advisory não bloqueia
    assert any("autenticidade" in f for f in parecer.flags)


def test_autenticidade_bloqueia_em_modo_estrito(make_tipo, tmp_path, monkeypatch):
    monkeypatch.setattr(conf, "_roteiros_recentes", lambda *a: ["antigo 1"])
    monkeypatch.setattr(conf.aut, "_chamar_api", lambda s, u, c: '{"sameness": 95}')
    tipo = _tipo_ativo(make_tipo, extra={"checagens": {"autenticidade": {"modo": "bloquear"}}})
    _sidecar(tmp_path / "run")
    parecer = conf.avaliar_publicacao(
        tipo, tmp_path / "run", {"visibilidade": {"disclosure_sintetico": True}}
    )
    assert parecer.bloqueado is True


def test_factual_off_por_padrao_nao_roda(make_tipo, tmp_path, monkeypatch):
    monkeypatch.setattr(conf, "_roteiros_recentes", lambda *a: [])
    def nao_deveria(roteiro, config):
        raise AssertionError("factual desligada não deveria rodar")
    monkeypatch.setattr(conf.fac, "verificar_factual", nao_deveria)
    tipo = _tipo_ativo(make_tipo)
    _sidecar(tmp_path / "run")
    parecer = conf.avaliar_publicacao(tipo, tmp_path / "run", {"visibilidade": {"disclosure_sintetico": True}})
    assert "factual" not in [c["nome"] for c in parecer.para_dict()["checagens"]]
