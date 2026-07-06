from api import formulario
from api.schemas import FeedbackConfig
from feedback.configuracao import (
    DESTINOS_FEEDBACK,
    DIMENSOES,
    FEEDBACK_PADRAO,
    METRICAS_DISPONIVEIS,
    MODOS_APLICACAO,
    UI_HINTS,
    mesclar_feedback,
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
    assert not (set(UI_HINTS) - _paths(FEEDBACK_PADRAO))


def test_ui_hints_opcoes_batem_com_default():
    for path, hint in UI_HINTS.items():
        if "opcoes" not in hint:
            continue
        val = FEEDBACK_PADRAO
        for p in path.split("."):
            val = val[p]
        if not isinstance(val, dict):
            assert val in hint["opcoes"], f"{path}: {val!r} fora de {hint['opcoes']}"


def test_parity_feedback_default_roundtrip():
    itens = formulario.arvore(FEEDBACK_PADRAO, FEEDBACK_PADRAO, UI_HINTS)

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

    recon = formulario.reagrupar(flat(itens, {}), FEEDBACK_PADRAO, UI_HINTS)
    # Pydantic recoage repoll_horas de list[str] -> list[int]; o dump deve bater.
    assert FeedbackConfig(**recon).model_dump() == FEEDBACK_PADRAO


def test_mesclar_none_devolve_padrao():
    out = mesclar_feedback(None)
    assert out == FEEDBACK_PADRAO
    assert out is not FEEDBACK_PADRAO  # cópia, não a referência


def test_mesclar_parcial_faz_deep_merge():
    out = mesclar_feedback({"destinos": {"youtube": {"ativo": True}}})
    assert out["destinos"]["youtube"]["ativo"] is True
    # o resto dos blocos é preservado do padrão
    assert out["sample_floor"] == 3
    assert out["repoll_horas"] == [24, 72, 168, 720]
    assert out["aplicacao"]["descoberta"] == "advisory"


def test_mesclar_substitui_lista_por_inteiro():
    # listas do bruto substituem, não fazem merge item-a-item
    out = mesclar_feedback({"repoll_horas": [48]})
    assert out["repoll_horas"] == [48]


def test_defaults_conservadores_pilar_inerte():
    p = FEEDBACK_PADRAO
    # destino off por default => nenhuma chamada de analytics
    assert p["destinos"]["youtube"]["ativo"] is False
    # aplicação advisory por default => gate humano
    assert p["aplicacao"] == {"descoberta": "advisory", "geracao": "advisory", "publicacao": "advisory"}
    # experimentos off
    assert p["experimentos"]["ativo"] is False
    # headline = retenção + CTR
    assert p["metricas"]["headline"] == ["avg_view_pct", "ctr"]


def test_enums_coerentes_com_default():
    assert set(FEEDBACK_PADRAO["metricas"]["ingeridas"]) <= set(METRICAS_DISPONIVEIS)
    assert set(FEEDBACK_PADRAO["dimensoes"]) <= set(DIMENSOES)
    assert set(FEEDBACK_PADRAO["destinos"]) <= set(DESTINOS_FEEDBACK)
    for alvo in FEEDBACK_PADRAO["aplicacao"].values():
        assert alvo in MODOS_APLICACAO


def test_schema_rejeita_metrica_invalida():
    import pytest
    from pydantic import ValidationError

    bruto = mesclar_feedback({"metricas": {"ingeridas": ["inexistente"]}})
    with pytest.raises(ValidationError):
        FeedbackConfig(**bruto)


def test_schema_rejeita_repoll_nao_positivo():
    import pytest
    from pydantic import ValidationError

    bruto = mesclar_feedback({"repoll_horas": [24, 0]})
    with pytest.raises(ValidationError):
        FeedbackConfig(**bruto)
