from geracao.configuracao import (
    ACOES_ORCAMENTO,
    FALLBACKS_VISUAIS,
    GERACAO_PADRAO,
    POSICOES_LEGENDA,
    PROVEDORES_NARRACAO,
    PROVEDORES_ROTEIRO,
    PROVEDORES_VISUAIS,
    mesclar_geracao,
)


def test_default_usa_enums_validos():
    assert GERACAO_PADRAO["roteiro"]["provedor"] in PROVEDORES_ROTEIRO
    assert GERACAO_PADRAO["visuais"]["provedor"] in PROVEDORES_VISUAIS
    assert GERACAO_PADRAO["visuais"]["fallback"] in FALLBACKS_VISUAIS
    assert GERACAO_PADRAO["narracao"]["provedor"] in PROVEDORES_NARRACAO
    assert GERACAO_PADRAO["legendas"]["posicao"] in POSICOES_LEGENDA
    assert GERACAO_PADRAO["orcamento"]["acao"] in ACOES_ORCAMENTO


def test_defaults_preservam_comportamento():
    # legendas/música/orçamento não disparam por padrão; checkpoint on
    assert GERACAO_PADRAO["legendas"]["ativo"] is False
    assert GERACAO_PADRAO["montagem"]["musica_fundo"]["ativo"] is False
    assert GERACAO_PADRAO["montagem"]["intro"] == ""
    assert GERACAO_PADRAO["checkpoint"]["reaproveitar"] is True
    # variação ligada baixa de propósito (escolha do usuário)
    assert GERACAO_PADRAO["variacao"]["aberturas"] == 0.3


def test_mesclar_none_devolve_default_completo():
    resultado = mesclar_geracao(None)
    assert resultado == GERACAO_PADRAO
    assert resultado is not GERACAO_PADRAO


def test_mesclar_preenche_chaves_ausentes():
    resultado = mesclar_geracao({"orcamento": {"acao": "parar"}})
    assert resultado["orcamento"]["acao"] == "parar"  # sobrescrito
    assert resultado["orcamento"]["por_video_usd"] == 1.0  # herdado
    assert resultado["roteiro"] == GERACAO_PADRAO["roteiro"]  # herdado


def test_mesclar_deep_merge_dentro_de_bloco():
    resultado = mesclar_geracao({"montagem": {"musica_fundo": {"ativo": True}}})
    assert resultado["montagem"]["musica_fundo"]["ativo"] is True
    assert resultado["montagem"]["musica_fundo"]["arquivo"] == ""  # herdado fundo
    assert resultado["montagem"]["intro"] == ""


def test_mesclar_nao_muta_o_default():
    mesclar_geracao({"variacao": {"aberturas": 0.9}})
    assert GERACAO_PADRAO["variacao"]["aberturas"] == 0.3
