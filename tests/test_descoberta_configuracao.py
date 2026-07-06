from api import formulario
from api.schemas import DescobertaConfig
from descoberta.configuracao import (
    DESCOBERTA_PADRAO,
    UI_HINTS,
    mesclar_descoberta,
)


def _paths(padrao, prefixo=""):
    """Todos os paths válidos (grupos e folhas) do PADRAO."""
    out = set()
    for chave, val in padrao.items():
        path = f"{prefixo}.{chave}" if prefixo else chave
        out.add(path)
        if isinstance(val, dict):
            out |= _paths(val, path)
    return out


def test_ui_hints_apontam_para_paths_reais():
    validos = _paths(DESCOBERTA_PADRAO)
    desconhecidos = set(UI_HINTS) - validos
    assert not desconhecidos, f"UI_HINTS com paths inexistentes: {desconhecidos}"


def test_ui_hints_opcoes_batem_com_o_default():
    # o valor default de cada select precisa estar entre as opções do hint
    for path, hint in UI_HINTS.items():
        if "opcoes" not in hint:
            continue
        partes = path.split(".")
        val = DESCOBERTA_PADRAO
        for p in partes:
            val = val[p]
        if not isinstance(val, dict):  # folha
            assert val in hint["opcoes"], f"{path}: default {val!r} fora de {hint['opcoes']}"


def test_parity_default_roundtrip():
    """arvore → form do browser → reagrupar → schema reproduz o PADRAO."""
    itens = formulario.arvore(DESCOBERTA_PADRAO, DESCOBERTA_PADRAO, UI_HINTS)

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

    form = flat(itens, {})
    recon = formulario.reagrupar(form, DESCOBERTA_PADRAO, UI_HINTS)
    assert DescobertaConfig(**recon).model_dump() == DESCOBERTA_PADRAO


def test_mesclar_none_devolve_default():
    assert mesclar_descoberta(None) == DESCOBERTA_PADRAO
    assert mesclar_descoberta(None) is not DESCOBERTA_PADRAO


def test_mesclar_preenche_e_nao_muta():
    r = mesclar_descoberta({"fit": {"score_minimo": 90}})
    assert r["fit"]["score_minimo"] == 90
    assert r["dedup"] == DESCOBERTA_PADRAO["dedup"]  # herdado
    assert DESCOBERTA_PADRAO["fit"]["score_minimo"] == 60  # não mutou
