from api import formulario
from api.schemas import PublicacaoConfig
from publicacao.configuracao import PUBLICACAO_PADRAO, UI_HINTS, mesclar_publicacao


def _paths(padrao, prefixo=""):
    out = set()
    for chave, val in padrao.items():
        path = f"{prefixo}.{chave}" if prefixo else chave
        out.add(path)
        if isinstance(val, dict):
            out |= _paths(val, path)
    return out


def test_ui_hints_apontam_para_paths_reais():
    assert not (set(UI_HINTS) - _paths(PUBLICACAO_PADRAO))


def test_ui_hints_opcoes_batem_com_default():
    for path, hint in UI_HINTS.items():
        if "opcoes" not in hint:
            continue
        val = PUBLICACAO_PADRAO
        for p in path.split("."):
            val = val[p]
        if not isinstance(val, dict):
            assert val in hint["opcoes"], f"{path}: {val!r} fora de {hint['opcoes']}"


def test_parity_publicacao_default_roundtrip():
    itens = formulario.arvore(PUBLICACAO_PADRAO, PUBLICACAO_PADRAO, UI_HINTS)

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

    recon = formulario.reagrupar(flat(itens, {}), PUBLICACAO_PADRAO, UI_HINTS)
    assert PublicacaoConfig(**recon).model_dump() == PUBLICACAO_PADRAO


def test_mesclar_none_devolve_padrao():
    out = mesclar_publicacao(None)
    assert out == PUBLICACAO_PADRAO
    assert out is not PUBLICACAO_PADRAO  # cópia, não a referência


def test_mesclar_parcial_faz_deep_merge():
    out = mesclar_publicacao({"thumbnail": {"ativo": True}})
    assert out["thumbnail"]["ativo"] is True
    # o resto do sub-bloco thumbnail é preservado do padrão
    assert out["thumbnail"]["fonte_fundo"] == "flux"
    assert out["thumbnail"]["texto"]["tamanho"] == 96
    # demais blocos intactos
    assert out["revisao"] == "auto"
    assert out["destinos"]["youtube"]["ativo"] is False


def test_migracao_do_youtube_legado_semeia_destino():
    legado = {
        "publicar": True,
        "categoria_id": "27",
        "tags": ["a", "b"],
        "descricao_base": "rodapé",
        "visibilidade": "unlisted",
    }
    out = mesclar_publicacao(None, legado)
    yt = out["destinos"]["youtube"]
    assert yt["ativo"] is True
    assert yt["categoria_id"] == "27"
    assert yt["tags_base"] == ["a", "b"]
    assert yt["descricao_base"] == "rodapé"
    assert out["visibilidade"]["privacidade"] == "unlisted"


def test_migracao_sem_publicar_mantem_destino_off():
    # cetico_pratico: youtube sem 'publicar' -> destino off (não publica, como hoje)
    out = mesclar_publicacao(None, {"categoria_id": "22", "visibilidade": "private"})
    assert out["destinos"]["youtube"]["ativo"] is False
    assert out["visibilidade"]["privacidade"] == "private"


def test_migracao_nao_sobrescreve_bloco_existente():
    # Se já existe um bloco publicacao salvo, o legado não migra por cima dele.
    bruto = {"destinos": {"youtube": {"ativo": False}}}
    out = mesclar_publicacao(bruto, {"publicar": True})
    assert out["destinos"]["youtube"]["ativo"] is False


def test_defaults_essenciais():
    p = PUBLICACAO_PADRAO
    assert p["revisao"] == "auto"
    assert p["timing"]["modo"] == "imediato"
    assert p["visibilidade"]["privacidade"] == "public"
    assert p["visibilidade"]["disclosure_sintetico"] is True
    assert p["thumbnail"]["ativo"] is False
    assert p["quota"]["cap_diario"] == 5
    assert p["destinos"]["youtube"]["ativo"] is False
