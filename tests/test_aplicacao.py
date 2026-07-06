from feedback import aplicacao, guia
from feedback.armazenamento import aplicados_de, propostas_de


# --- aplicar numérico / set (reversível) ------------------------------------


def test_aplica_numerico_e_registra(make_tipo):
    tipo = make_tipo("tipo_teste")
    antigo = tipo.config.get("descoberta.evergreen_ratio")
    prop = {"tipo": "numerico", "pilar": "descoberta", "alvo": "descoberta.evergreen_ratio",
            "valor_atual": antigo, "valor_novo": 0.25, "dimensao": "categoria"}
    ap = aplicacao.aplicar(tipo, prop)

    from config.tipos import carregar_tipo
    assert carregar_tipo("tipo_teste").config.get("descoberta.evergreen_ratio") == 0.25
    assert ap["valor_antigo"] == antigo
    assert ap["valor_novo"] == 0.25
    assert aplicados_de(tipo).listar()[0]["alvo"] == "descoberta.evergreen_ratio"


def test_reverter_numerico_restaura(make_tipo):
    tipo = make_tipo("tipo_teste")
    antigo = tipo.config.get("descoberta.evergreen_ratio")
    ap = aplicacao.aplicar(tipo, {"tipo": "numerico", "alvo": "descoberta.evergreen_ratio",
                                  "valor_novo": 0.9, "valor_atual": antigo})
    aplicacao.reverter(tipo, ap)
    from config.tipos import carregar_tipo
    assert carregar_tipo("tipo_teste").config.get("descoberta.evergreen_ratio") == antigo


def test_aplica_set_categorico(make_tipo):
    tipo = make_tipo("tipo_teste")  # imagens.modo = personagem
    ap = aplicacao.aplicar(tipo, {"tipo": "set", "alvo": "imagens.modo",
                                  "valor_atual": "personagem", "valor_novo": "ia", "dimensao": "modo_visual"})
    from config.tipos import carregar_tipo
    assert carregar_tipo("tipo_teste").config.get("imagens.modo") == "ia"
    assert ap["valor_antigo"] == "personagem"


def test_aplica_preserva_irmaos(make_tipo):
    tipo = make_tipo("tipo_teste")
    voz = tipo.config.get("tts.voz")
    aplicacao.aplicar(tipo, {"tipo": "numerico", "alvo": "geracao.roteiro.duracao_alvo_seg",
                             "valor_novo": 50, "valor_atual": 60})
    from config.tipos import carregar_tipo
    t = carregar_tipo("tipo_teste")
    assert t.config.get("tts.voz") == voz  # bloco irmão intacto
    assert t.config.get("geracao.roteiro.duracao_alvo_seg") == 50


# --- aplicar guia (reversível) ----------------------------------------------


def test_aplica_guia_escreve_bloco(make_tipo):
    tipo = make_tipo("tipo_teste")
    prop = {"tipo": "guia", "pilar": "geracao", "alvo": "guia:roteiro", "bloco": "roteiro",
            "dimensao": "hook", "confianca": 0.7, "linhas_novas": ["Abra com pergunta"]}
    ap = aplicacao.aplicar(tipo, prop)
    assert guia.compor(tipo.assets_dir, "roteiro", "BASE").endswith("- Abra com pergunta")
    assert ap["linhas_novas"] == ["Abra com pergunta"]
    assert ap["linhas_antigas"] == []


def test_reverter_guia_restaura(make_tipo):
    tipo = make_tipo("tipo_teste")
    guia.bloco_de(tipo.assets_dir, "roteiro").substituir([guia.linha("Original")])
    prop = {"tipo": "guia", "bloco": "roteiro", "alvo": "guia:roteiro",
            "linhas_novas": ["Nova"], "dimensao": "hook"}
    ap = aplicacao.aplicar(tipo, prop)
    assert [l["texto"] for l in guia.bloco_de(tipo.assets_dir, "roteiro").linhas_ativas()] == ["Nova"]
    aplicacao.reverter(tipo, ap)
    assert [l["texto"] for l in guia.bloco_de(tipo.assets_dir, "roteiro").linhas_ativas()] == ["Original"]


# --- gate advisory: aprovar / rejeitar --------------------------------------


def test_aprovar_aplica_e_marca(make_tipo):
    tipo = make_tipo("tipo_teste")
    antigo = tipo.config.get("descoberta.evergreen_ratio")
    reg = propostas_de(tipo).adicionar({"tipo": "numerico", "alvo": "descoberta.evergreen_ratio",
                                        "valor_novo": 0.4, "valor_atual": antigo, "pilar": "descoberta"})
    ap = aplicacao.aprovar(tipo, reg["id"])
    assert ap is not None
    from config.tipos import carregar_tipo
    assert carregar_tipo("tipo_teste").config.get("descoberta.evergreen_ratio") == 0.4
    assert propostas_de(tipo).obter(reg["id"])["status"] == "aprovada"


def test_rejeitar_nao_aplica(make_tipo):
    tipo = make_tipo("tipo_teste")
    antigo = tipo.config.get("descoberta.evergreen_ratio")
    reg = propostas_de(tipo).adicionar({"tipo": "numerico", "alvo": "descoberta.evergreen_ratio",
                                        "valor_novo": 0.4, "valor_atual": antigo})
    aplicacao.rejeitar(tipo, reg["id"])
    from config.tipos import carregar_tipo
    assert carregar_tipo("tipo_teste").config.get("descoberta.evergreen_ratio") == antigo
    assert propostas_de(tipo).obter(reg["id"])["status"] == "rejeitada"


def test_aprovar_inexistente_ou_ja_resolvida(make_tipo):
    tipo = make_tipo("tipo_teste")
    assert aplicacao.aprovar(tipo, "naoexiste") is None
    reg = propostas_de(tipo).adicionar({"tipo": "set", "alvo": "imagens.modo", "valor_novo": "ia"})
    propostas_de(tipo).definir_status(reg["id"], "rejeitada")
    assert aplicacao.aprovar(tipo, reg["id"]) is None  # não re-aplica uma já resolvida
