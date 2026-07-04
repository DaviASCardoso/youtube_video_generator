from descoberta.balanco import categoria_do_ciclo


def test_ratio_zero_sempre_trending():
    assert categoria_do_ciclo(["evergreen", "evergreen"], 0.0) == "trending"


def test_ratio_um_sempre_evergreen():
    assert categoria_do_ciclo(["trending"], 1.0) == "evergreen"


def test_sem_historico_segue_o_lado_do_alvo():
    assert categoria_do_ciclo([], 0.3) == "trending"
    assert categoria_do_ciclo([], 0.7) == "evergreen"


def test_puxa_para_evergreen_quando_abaixo_do_alvo():
    # 0 de 4 evergreen, alvo 0.3 -> falta evergreen
    assert categoria_do_ciclo(["trending"] * 4, 0.3) == "evergreen"


def test_puxa_para_trending_quando_acima_do_alvo():
    # 3 de 4 evergreen (0.75), alvo 0.3 -> já passou, vai de trending
    assert categoria_do_ciclo(["evergreen", "evergreen", "evergreen", "trending"], 0.3) == "trending"
