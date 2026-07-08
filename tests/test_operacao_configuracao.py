from api import formulario
from api.schemas import OperacaoConfig
from operacoes.configuracao import (
    ESTAGIOS,
    JOBS,
    OPERACAO_PADRAO,
    POLITICAS_PARCIAL,
    UI_HINTS,
    mesclar_operacao,
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
    assert not (set(UI_HINTS) - _paths(OPERACAO_PADRAO))


def test_ui_hints_opcoes_batem_com_default():
    for path, hint in UI_HINTS.items():
        if "opcoes" not in hint:
            continue
        val = OPERACAO_PADRAO
        for p in path.split("."):
            val = val[p]
        if not isinstance(val, dict):
            assert val in hint["opcoes"], f"{path}: {val!r} fora de {hint['opcoes']}"


def test_parity_operacao_default_roundtrip():
    itens = formulario.arvore(OPERACAO_PADRAO, OPERACAO_PADRAO, UI_HINTS)

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

    recon = formulario.reagrupar(flat(itens, {}), OPERACAO_PADRAO, UI_HINTS)
    assert OperacaoConfig(**recon).model_dump() == OPERACAO_PADRAO


def test_mesclar_none_devolve_padrao():
    out = mesclar_operacao(None)
    assert out == OPERACAO_PADRAO
    assert out is not OPERACAO_PADRAO


def test_mesclar_parcial_faz_deep_merge():
    out = mesclar_operacao({"backoff": {"base_seg": 5.0}})
    assert out["backoff"]["base_seg"] == 5.0
    # resto do backoff preservado
    assert out["backoff"]["teto_seg"] == 60.0
    assert out["backoff"]["jitter"] == 0.5
    # demais blocos intactos
    assert out["failover"] is True
    assert out["caps_por_estagio"]["visuais"] == 2


def test_defaults_equivalem_ao_comportamento_de_hoje():
    p = OPERACAO_PADRAO
    # 3 retries no roteiro (== TENTATIVAS de hoje), mais apertado nos caros
    assert p["caps_por_estagio"]["roteiro"] == 3
    assert p["caps_por_estagio"]["visuais"] == 2
    assert p["caps_por_estagio"]["narracao"] == 2
    assert p["backoff"]["base_seg"] == 2.0  # == ESPERA_BACKOFF de hoje
    assert p["failover"] is True
    assert p["falha_parcial"] == "degradar"
    # todos os jobs ligados por default
    assert all(p["jobs"].values())


def test_enums_coerentes_com_default():
    assert set(OPERACAO_PADRAO["jobs"]) == set(JOBS)
    assert set(OPERACAO_PADRAO["caps_por_estagio"]) == set(ESTAGIOS)
    assert OPERACAO_PADRAO["falha_parcial"] in POLITICAS_PARCIAL


def test_schema_rejeita_falha_parcial_invalida():
    import pytest
    from pydantic import ValidationError

    bruto = mesclar_operacao({"falha_parcial": "explodir"})
    with pytest.raises(ValidationError):
        OperacaoConfig(**bruto)
