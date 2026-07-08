from api import formulario
from api.schemas import ConformidadeConfig
from conformidade.configuracao import (
    CHECAGENS,
    CONFORMIDADE_PADRAO,
    ESTRATEGIAS,
    MODOS_CHECK,
    UI_HINTS,
    mesclar_conformidade,
)


def _paths(padrao, prefixo=""):
    out = set()
    for chave, val in padrao.items():
        path = f"{prefixo}.{chave}" if prefixo else chave
        out.add(path)
        if isinstance(val, dict):
            out |= _paths(val, path)
    return out


def test_ui_hints_apontam_para_paths_reais():
    assert not (set(UI_HINTS) - _paths(CONFORMIDADE_PADRAO))


def test_ui_hints_opcoes_batem_com_default():
    for path, hint in UI_HINTS.items():
        if "opcoes" not in hint:
            continue
        val = CONFORMIDADE_PADRAO
        for p in path.split("."):
            val = val[p]
        if not isinstance(val, dict):
            assert val in hint["opcoes"], f"{path}: {val!r} fora de {hint['opcoes']}"


def test_parity_conformidade_default_roundtrip():
    itens = formulario.arvore(CONFORMIDADE_PADRAO, CONFORMIDADE_PADRAO, UI_HINTS)

    def flat(itens, out):
        for it in itens:
            if it.kind == "grupo":
                flat(it.itens, out)
            elif it.tipo == "checkbox":
                if it.valor:
                    out[it.nome] = "on"
            elif it.tipo == "lista":
                out[it.nome] = "\n".join(str(x) for x in it.valor)
            elif it.valor is None:
                out[it.nome] = ""
            else:
                out[it.nome] = str(it.valor)
        return out

    recon = formulario.reagrupar(flat(itens, {}), CONFORMIDADE_PADRAO, UI_HINTS)
    assert ConformidadeConfig(**recon).model_dump() == CONFORMIDADE_PADRAO


def test_mesclar_none_devolve_padrao():
    out = mesclar_conformidade(None)
    assert out == CONFORMIDADE_PADRAO
    assert out is not CONFORMIDADE_PADRAO


def test_mesclar_parcial_faz_deep_merge():
    out = mesclar_conformidade({"ativo": True, "checagens": {"autenticidade": {"teto_sameness": 55}}})
    assert out["ativo"] is True
    # o resto de autenticidade preservado
    assert out["checagens"]["autenticidade"]["teto_sameness"] == 55
    assert out["checagens"]["autenticidade"]["variacao_minima"] == 0.25
    assert out["checagens"]["autenticidade"]["modo"] == "advisory"
    # demais checagens intactas
    assert out["checagens"]["disclosure"]["modo"] == "bloquear"


def test_defaults_sao_inertes_e_seguem_a_spec():
    p = CONFORMIDADE_PADRAO
    assert p["ativo"] is False  # inerte por padrão → comportamento equivalente
    # objetivas bloqueiam
    assert p["checagens"]["disclosure"]["modo"] == "bloquear"
    assert p["checagens"]["licenciamento"]["modo"] == "bloquear"
    # brand safety: bloqueia inequívoco, sinaliza limítrofe
    assert p["checagens"]["marca"]["modo"] == "equilibrada"
    # subjetivas avisam
    assert p["checagens"]["autenticidade"]["modo"] == "advisory"
    assert p["checagens"]["factual"]["modo"] == "advisory"
    # factual desligada por padrão
    assert p["checagens"]["factual"]["ativo"] is False


def test_enums_coerentes_com_default():
    assert set(CONFORMIDADE_PADRAO["checagens"]) == set(CHECAGENS)
    assert CONFORMIDADE_PADRAO["estrategia"] in ESTRATEGIAS
    for chave in ("disclosure", "licenciamento", "marca", "autenticidade", "factual"):
        assert CONFORMIDADE_PADRAO["checagens"][chave]["modo"] in MODOS_CHECK


def test_schema_rejeita_modo_invalido():
    import pytest
    from pydantic import ValidationError

    bruto = mesclar_conformidade({"checagens": {"disclosure": {"modo": "explodir"}}})
    with pytest.raises(ValidationError):
        ConformidadeConfig(**bruto)


def test_schema_rejeita_estrategia_invalida():
    import pytest
    from pydantic import ValidationError

    bruto = mesclar_conformidade({"estrategia": "caótica"})
    with pytest.raises(ValidationError):
        ConformidadeConfig(**bruto)
