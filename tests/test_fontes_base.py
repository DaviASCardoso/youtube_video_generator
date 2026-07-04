from descoberta.fontes import base


def test_candidatos_por_rank_filtra_e_ordena():
    cands = base.candidatos_por_rank(["Primeiro", "", "   ", "Segundo", 5], "x")
    assert [c.texto for c in cands] == ["Primeiro", "Segundo"]
    assert cands[0].forca_sinal > cands[1].forca_sinal
    assert all(c.fonte == "x" and c.categoria == "trending" for c in cands)


def test_candidatos_por_rank_categoria_customizada():
    cands = base.candidatos_por_rank(["A"], "pool", categoria="evergreen")
    assert cands[0].categoria == "evergreen"


def test_coletar_fonte_desconhecida_retorna_vazio():
    assert base.coletar("nao_existe_xyz", None, {}) == []


def test_coletar_degrada_em_excecao():
    @base.registrar("fonte_que_quebra")
    def _quebra(tipo, cfg):
        raise RuntimeError("boom")

    assert base.coletar("fonte_que_quebra", None, {}) == []


def test_coletar_retorna_candidatos_da_fonte():
    @base.registrar("fonte_ok")
    def _ok(tipo, cfg):
        return base.candidatos_por_rank(["A", "B"], "fonte_ok")

    assert base.registrada("fonte_ok")
    out = base.coletar("fonte_ok", None, {})
    assert [c.texto for c in out] == ["A", "B"]
