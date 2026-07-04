from descoberta.configuracao import (
    CATEGORIAS,
    DESCOBERTA_PADRAO,
    ESTRATEGIAS_DEDUP,
    FONTES_DISPONIVEIS,
    MODOS_REVIEW,
    POLITICAS_RETENCAO,
    mesclar_descoberta,
)


def test_default_tem_todas_as_fontes():
    assert set(DESCOBERTA_PADRAO["fontes"]) == set(FONTES_DISPONIVEIS)


def test_default_youtube_desligado_demais_ligadas():
    fontes = DESCOBERTA_PADRAO["fontes"]
    assert fontes["youtube"]["ativo"] is False
    for nome in FONTES_DISPONIVEIS:
        if nome != "youtube":
            assert fontes[nome]["ativo"] is True


def test_default_usa_enums_validos():
    assert DESCOBERTA_PADRAO["dedup"]["estrategia"] in ESTRATEGIAS_DEDUP
    assert DESCOBERTA_PADRAO["modo_revisao"] in MODOS_REVIEW
    assert DESCOBERTA_PADRAO["retencao"] in POLITICAS_RETENCAO


def test_categorias_conhecidas():
    assert set(CATEGORIAS) == {"trending", "evergreen"}


def test_mesclar_none_devolve_default_completo():
    resultado = mesclar_descoberta(None)
    assert resultado == DESCOBERTA_PADRAO
    # é uma cópia, não o próprio objeto (não deve vazar mutação)
    assert resultado is not DESCOBERTA_PADRAO


def test_mesclar_preenche_chaves_ausentes():
    resultado = mesclar_descoberta({"fit": {"score_minimo": 90}})
    assert resultado["fit"]["score_minimo"] == 90  # sobrescrito
    assert resultado["dedup"] == DESCOBERTA_PADRAO["dedup"]  # herdado
    assert resultado["fontes"]["reddit"]["ativo"] is True  # herdado fundo


def test_mesclar_deep_merge_dentro_de_fonte():
    # muda só um campo de uma fonte; os demais campos daquela fonte permanecem
    resultado = mesclar_descoberta({"fontes": {"reddit": {"ativo": False}}})
    assert resultado["fontes"]["reddit"]["ativo"] is False
    assert resultado["fontes"]["reddit"]["limite"] == DESCOBERTA_PADRAO["fontes"]["reddit"]["limite"]
    assert resultado["fontes"]["reddit"]["periodo"] == "day"


def test_mesclar_nao_muta_o_default():
    mesclar_descoberta({"fontes": {"reddit": {"subreddits": ["outro"]}}})
    assert DESCOBERTA_PADRAO["fontes"]["reddit"]["subreddits"] == ["brasil"]
