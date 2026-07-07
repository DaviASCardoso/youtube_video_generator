"""Parity dos formulários schema-driven da aba Config e das Configurações globais."""

from api import formulario
from api.routers import tipos as T
from api.schemas import SistemaConfig, TipoConfig
from config.sistema import SISTEMA_PADRAO, UI_HINTS as SISTEMA_UI_HINTS


def _flat(itens, out):
    for it in itens:
        if it.kind == "grupo":
            _flat(it.itens, out)
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


def _paths(padrao, prefixo=""):
    out = set()
    for chave, val in padrao.items():
        path = f"{prefixo}.{chave}" if prefixo else chave
        out.add(path)
        if isinstance(val, dict):
            out |= _paths(val, path)
    return out


# --- Configurações globais (sistema.json) -----------------------------------


def test_sistema_hints_validos():
    assert not (set(SISTEMA_UI_HINTS) - _paths(SISTEMA_PADRAO))


def test_sistema_parity_default():
    itens = formulario.arvore(SISTEMA_PADRAO, SISTEMA_PADRAO, SISTEMA_UI_HINTS)
    recon = formulario.reagrupar(_flat(itens, {}), SISTEMA_PADRAO, SISTEMA_UI_HINTS)
    assert SistemaConfig(**recon).model_dump() == SISTEMA_PADRAO


# --- Aba Config do tipo -----------------------------------------------------


def test_config_tab_hints_validos():
    assert not (set(T.UI_HINTS_CONFIG) - _paths(T.CONFIG_TAB_PADRAO))


def test_config_tab_hints_opcoes_batem_com_default():
    for path, hint in T.UI_HINTS_CONFIG.items():
        if "opcoes" not in hint:
            continue
        val = T.CONFIG_TAB_PADRAO
        for p in path.split("."):
            val = val[p]
        if not isinstance(val, dict):
            assert val in hint["opcoes"], f"{path}: {val!r} fora de {hint['opcoes']}"


def test_config_tab_nao_expoe_blocos_de_pilar():
    # os blocos de pilar têm abas próprias e não devem aparecer na aba Config
    for bloco in ("descoberta", "geracao", "publicacao", "feedback", "operacao"):
        assert bloco not in T.CONFIG_TAB_PADRAO


def test_config_tab_parity_default():
    itens = formulario.arvore(T.CONFIG_TAB_PADRAO, T.CONFIG_TAB_PADRAO, T.UI_HINTS_CONFIG)
    recon = formulario.reagrupar(_flat(itens, {}), T.CONFIG_TAB_PADRAO, T.UI_HINTS_CONFIG)
    assert recon == T.CONFIG_TAB_PADRAO


def test_config_tab_roundtrip_valida_no_schema(make_tipo):
    """Round-trip de um tipo real reproduz um config que valida no TipoConfig e é
    ponto-fixo (salvar de novo não muda nada)."""
    from descoberta.configuracao import mesclar_descoberta
    from feedback.configuracao import mesclar_feedback
    from geracao.configuracao import mesclar_geracao
    from operacoes.configuracao import mesclar_operacao
    from publicacao.configuracao import mesclar_publicacao

    tipo = make_tipo()

    def rt(atual):
        itens = formulario.arvore(T.CONFIG_TAB_PADRAO, atual, T.UI_HINTS_CONFIG)
        recon = formulario.reagrupar(_flat(itens, {}), T.CONFIG_TAB_PADRAO, T.UI_HINTS_CONFIG)
        full = {
            **recon,
            "descoberta": mesclar_descoberta(atual.get("descoberta")),
            "geracao": mesclar_geracao(atual.get("geracao")),
            "publicacao": mesclar_publicacao(atual.get("publicacao"), atual.get("youtube")),
            "feedback": mesclar_feedback(atual.get("feedback")),
            "operacao": mesclar_operacao(atual.get("operacao")),
        }
        return TipoConfig(**full).model_dump()

    s1 = rt(tipo.config.get_all())
    assert rt(s1) == s1  # ponto-fixo
