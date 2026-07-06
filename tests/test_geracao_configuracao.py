from api import formulario
from api.schemas import GeracaoConfig
from geracao.configuracao import (
    ACOES_ORCAMENTO,
    FALLBACKS_VISUAIS,
    GERACAO_PADRAO,
    POSICOES_LEGENDA,
    PROVEDORES_NARRACAO,
    PROVEDORES_ROTEIRO,
    PROVEDORES_VISUAIS,
    UI_HINTS,
    mesclar_geracao,
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
    assert not (set(UI_HINTS) - _paths(GERACAO_PADRAO))


def test_ui_hints_opcoes_batem_com_default():
    for path, hint in UI_HINTS.items():
        if "opcoes" not in hint:
            continue
        val = GERACAO_PADRAO
        for p in path.split("."):
            val = val[p]
        if not isinstance(val, dict):
            assert val in hint["opcoes"], f"{path}: {val!r} fora de {hint['opcoes']}"


def test_parity_geracao_default_roundtrip():
    itens = formulario.arvore(GERACAO_PADRAO, GERACAO_PADRAO, UI_HINTS)

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

    recon = formulario.reagrupar(flat(itens, {}), GERACAO_PADRAO, UI_HINTS)
    assert GeracaoConfig(**recon).model_dump() == GERACAO_PADRAO


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
