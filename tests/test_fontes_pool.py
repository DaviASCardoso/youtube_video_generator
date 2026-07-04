from descoberta.fontes import pool


def test_manual_le_so_ideias_manuais(make_tipo):
    tipo = make_tipo()
    tipo.temas.adicionar("Ideia manual", 90, fonte="manual")
    tipo.temas.adicionar("Tema evergreen", 80, fonte="evergreen")
    tipo.temas.adicionar("Legado trends", 70, fonte="trends")

    man = pool.buscar_manual(tipo, {})
    assert [c.texto for c in man] == ["Ideia manual"]
    assert man[0].fonte == "manual"
    assert man[0].categoria == "trending"


def test_evergreen_le_so_ideias_evergreen(make_tipo):
    tipo = make_tipo()
    tipo.temas.adicionar("Atemporal", 80, fonte="evergreen")
    tipo.temas.adicionar("Manual", 90, fonte="manual")

    ev = pool.buscar_evergreen(tipo, {})
    assert [c.texto for c in ev] == ["Atemporal"]
    assert ev[0].categoria == "evergreen"


def test_pool_ordena_por_prioridade(make_tipo):
    tipo = make_tipo()
    tipo.temas.adicionar("Baixa", 10, fonte="manual")
    tipo.temas.adicionar("Alta", 90, fonte="manual")

    man = pool.buscar_manual(tipo, {})
    assert [c.texto for c in man] == ["Alta", "Baixa"]
    assert man[0].forca_sinal > man[1].forca_sinal


def test_pool_vazio_sem_ideias_da_categoria(make_tipo):
    tipo = make_tipo()
    tipo.temas.adicionar("Legado", 50, fonte="trends")
    assert pool.buscar_manual(tipo, {}) == []
    assert pool.buscar_evergreen(tipo, {}) == []
