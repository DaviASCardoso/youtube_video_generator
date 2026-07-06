from feedback import armazenamento as arm


# --- MetricasStore ----------------------------------------------------------


def test_metricas_grava_e_le_por_video(make_tipo):
    tipo = make_tipo()
    m = arm.metricas_de(tipo)
    assert m.video("vid1") is None
    m.gravar_video("vid1", {"avg_view_pct": 55.0, "curva": [1.0, 0.8, 0.6]})
    reg = m.video("vid1")
    assert reg["avg_view_pct"] == 55.0
    assert reg["curva"] == [1.0, 0.8, 0.6]
    assert reg["atualizado_em"]  # carimbado


def test_metricas_lista_videos(make_tipo):
    tipo = make_tipo()
    m = arm.metricas_de(tipo)
    m.gravar_video("a", {"views": 10})
    m.gravar_video("b", {"views": 20})
    ids = {v["id"] for v in m.videos()}
    assert ids == {"a", "b"}


def test_metricas_arquivo_corrompido_degrada(make_tipo):
    tipo = make_tipo()
    m = arm.metricas_de(tipo)
    m._caminho.parent.mkdir(parents=True, exist_ok=True)
    m._caminho.write_text("{lixo", encoding="utf-8")
    assert m.ler() == {}


# --- FindingsStore ----------------------------------------------------------


def test_findings_substitui_e_le(make_tipo):
    tipo = make_tipo()
    f = arm.findings_de(tipo)
    assert f.itens() == []
    f.substituir([{"dimensao": "hook", "efeito": 0.3}], assinatura="abc")
    assert f.itens()[0]["dimensao"] == "hook"
    assert f.assinatura() == "abc"
    assert f.ler()["calculado_em"]


def test_findings_substituir_troca_tudo(make_tipo):
    tipo = make_tipo()
    f = arm.findings_de(tipo)
    f.substituir([{"dimensao": "a"}])
    f.substituir([{"dimensao": "b"}])
    assert [i["dimensao"] for i in f.itens()] == ["b"]


# --- PropostasStore ---------------------------------------------------------


def test_propostas_adiciona_com_id_e_status(make_tipo):
    tipo = make_tipo()
    p = arm.propostas_de(tipo)
    reg = p.adicionar({"tipo": "numerico", "alvo": "descoberta"})
    assert reg["id"]
    assert reg["status"] == "pendente"
    assert reg["criado_em"]
    assert p.obter(reg["id"])["alvo"] == "descoberta"


def test_propostas_pendentes_filtra_status(make_tipo):
    tipo = make_tipo()
    p = arm.propostas_de(tipo)
    r1 = p.adicionar({"tipo": "guia"})
    p.adicionar({"tipo": "numerico"})
    p.definir_status(r1["id"], "aprovada")
    pend = p.pendentes()
    assert len(pend) == 1
    assert pend[0]["tipo"] == "numerico"


def test_propostas_remover(make_tipo):
    tipo = make_tipo()
    p = arm.propostas_de(tipo)
    r = p.adicionar({"tipo": "guia"})
    assert p.remover(r["id"]) is True
    assert p.obter(r["id"]) is None
    assert p.remover("inexistente") is False


def test_propostas_idempotencia_por_chave(make_tipo):
    tipo = make_tipo()
    p = arm.propostas_de(tipo)
    p.adicionar({"tipo": "numerico", "chave": "descoberta.evergreen_ratio"})
    assert p.existe_equivalente("descoberta.evergreen_ratio") is True
    assert p.existe_equivalente("outra") is False
    assert p.existe_equivalente("") is False


def test_propostas_definir_status_carimba(make_tipo):
    tipo = make_tipo()
    p = arm.propostas_de(tipo)
    r = p.adicionar({"tipo": "guia"})
    atualizada = p.definir_status(r["id"], "rejeitada")
    assert atualizada["status"] == "rejeitada"
    assert atualizada["resolvido_em"]
    assert p.definir_status("inexistente", "x") is None


# --- AplicadosStore ---------------------------------------------------------


def test_aplicados_registra_e_lista(make_tipo):
    tipo = make_tipo()
    a = arm.aplicados_de(tipo)
    a.registrar({"path": "descoberta.evergreen_ratio", "valor_antigo": 0.3, "valor_novo": 0.4})
    a.registrar({"path": "publicacao.timing.horario", "valor_antigo": "18:00", "valor_novo": "19:00"})
    itens = a.listar()
    assert len(itens) == 2
    # mais recente primeiro
    assert itens[0]["path"] == "publicacao.timing.horario"
    assert itens[0]["aplicado_em"]


def test_stores_isolados_por_tipo(make_tipo):
    t1 = make_tipo("t1")
    t2 = make_tipo("t2")
    arm.metricas_de(t1).gravar_video("v", {"views": 1})
    assert arm.metricas_de(t2).ler() == {}
