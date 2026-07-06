from api import formulario as f

PADRAO = {
    "ativo": True,
    "nome": "x",
    "quantidade": 5,
    "peso": 0.3,
    "tags": [],
    "semente": None,
    "grupo": {"modo": "auto", "avancado_val": 10},
}

HINTS = {
    "grupo": {"rotulo": "Grupo X", "avancado": True},
    "grupo.modo": {"opcoes": ("auto", "manual"), "rotulo": "Modo"},
    "semente": {"tipo": "number", "ajuda": "vazio = aleatória"},
}


def _campos_planos(itens):
    """Achata a árvore em Campos (ignora a estrutura de grupos)."""
    planos = []
    for it in itens:
        if it.kind == "grupo":
            planos.extend(_campos_planos(it.itens))
        else:
            planos.append(it)
    return planos


def _por_path(itens):
    return {c.path: c for c in _campos_planos(itens)}


# --- arvore ------------------------------------------------------------------


def test_inferencia_de_tipos():
    campos = _por_path(f.arvore(PADRAO, {}, HINTS))
    assert campos["ativo"].tipo == "checkbox"
    assert campos["quantidade"].tipo == "number" and campos["quantidade"].passo == "1"
    assert campos["peso"].tipo == "number" and campos["peso"].passo == "any"
    assert campos["tags"].tipo == "lista"
    assert campos["semente"].tipo == "number"  # forçado pelo hint
    assert campos["grupo.modo"].tipo == "select"
    assert campos["grupo.modo"].opcoes == [("auto", "auto"), ("manual", "manual")]


def test_grupo_avancado_e_rotulo():
    itens = f.arvore(PADRAO, {}, HINTS)
    grupos = [it for it in itens if it.kind == "grupo"]
    assert len(grupos) == 1
    g = grupos[0]
    assert g.rotulo == "Grupo X"
    assert g.avancado is True
    assert {c.path for c in g.itens} == {"grupo.modo", "grupo.avancado_val"}


def test_nome_form_achatado():
    campos = _por_path(f.arvore(PADRAO, {}, HINTS))
    assert campos["grupo.modo"].nome == "grupo__modo"


def test_override_detectado():
    atual = {"quantidade": 9, "grupo": {"modo": "manual"}}
    campos = _por_path(f.arvore(PADRAO, atual, HINTS))
    assert campos["quantidade"].override is True
    assert campos["quantidade"].valor == 9
    assert campos["grupo.modo"].override is True
    assert campos["ativo"].override is False  # igual ao default


def test_humanizar_rotulo_default():
    campos = _por_path(f.arvore(PADRAO, {}, HINTS))
    assert campos["grupo.avancado_val"].rotulo == "Avancado val"


def test_oculto_pula_campo():
    hints = {**HINTS, "peso": {"oculto": True}}
    campos = _por_path(f.arvore(PADRAO, {}, hints))
    assert "peso" not in campos


def test_default_exibicao():
    campos = _por_path(f.arvore(PADRAO, {}, HINTS))
    assert campos["ativo"].default_exibicao == "sim"
    assert campos["tags"].default_exibicao == "—"
    assert campos["semente"].default_exibicao == "—"


# --- reagrupar ---------------------------------------------------------------


def test_reagrupar_coage_tipos():
    form = {
        "ativo": "on",  # checkbox presente = True
        "nome": "olá",
        "quantidade": "12",
        "peso": "0.75",
        "tags": "a, b\nc",
        "semente": "42",
        "grupo__modo": "manual",
        "grupo__avancado_val": "3",
    }
    out = f.reagrupar(form, PADRAO, HINTS)
    assert out["ativo"] is True
    assert out["nome"] == "olá"
    assert out["quantidade"] == 12 and isinstance(out["quantidade"], int)
    assert out["peso"] == 0.75 and isinstance(out["peso"], float)
    assert out["tags"] == ["a", "b", "c"]
    assert out["semente"] == 42
    assert out["grupo"] == {"modo": "manual", "avancado_val": 3}


def test_reagrupar_checkbox_ausente_false():
    out = f.reagrupar({"nome": "x"}, PADRAO, HINTS)
    assert out["ativo"] is False


def test_reagrupar_semente_vazia_none():
    out = f.reagrupar({"semente": "  "}, PADRAO, HINTS)
    assert out["semente"] is None


def test_reagrupar_numero_invalido_cai_no_default():
    out = f.reagrupar({"quantidade": "abc"}, PADRAO, HINTS)
    assert out["quantidade"] == 5  # default


def test_reagrupar_ignora_campos_desconhecidos():
    out = f.reagrupar({"intruso": "x", "nome": "y"}, PADRAO, HINTS)
    assert "intruso" not in out
    assert set(out.keys()) == set(PADRAO.keys())


def test_reagrupar_respeita_oculto():
    hints = {**HINTS, "peso": {"oculto": True}}
    out = f.reagrupar({"peso": "0.9"}, PADRAO, hints)
    assert "peso" not in out


# --- roundtrip ---------------------------------------------------------------


def _form_da_arvore(itens):
    """Reconstrói um form flat a partir dos valores atuais da árvore (como o browser faria)."""
    form = {}
    for c in _campos_planos(itens):
        if c.tipo == "checkbox":
            if c.valor:
                form[c.nome] = "on"
        elif c.tipo == "lista":
            form[c.nome] = "\n".join(str(x) for x in c.valor)
        elif c.valor is None:
            form[c.nome] = ""
        else:
            form[c.nome] = str(c.valor)
    return form


def test_roundtrip_arvore_reagrupar():
    atual = {
        "ativo": False,
        "nome": "canal",
        "quantidade": 7,
        "peso": 0.9,
        "tags": ["x", "y"],
        "semente": 3,
        "grupo": {"modo": "manual", "avancado_val": 42},
    }
    itens = f.arvore(PADRAO, atual, HINTS)
    form = _form_da_arvore(itens)
    reconstruido = f.reagrupar(form, PADRAO, HINTS)
    assert reconstruido == atual
