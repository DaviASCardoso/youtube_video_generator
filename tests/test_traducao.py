import json

from feedback import guia, traducao
from feedback.configuracao import mesclar_feedback

CFG = mesclar_feedback({"guia": {"top_k": 3, "tamanho_max_chars": 800}})


def _finding_hook(exemplos=None):
    return {
        "dimensao": "hook", "tipo": "textual", "valor": None, "efeito": 12.0,
        "n": 5, "confianca": 0.6, "metrica": "avg_view_pct",
        "exemplos": exemplos or ["Comece com uma pergunta desconfortável"],
        "piores": [],
    }


def _mock_groq(monkeypatch, retorno):
    """retorno: str (resposta crua do modelo) ou Exception."""
    import geracao.generate_script as gs

    def _fake(system, user, config):
        if isinstance(retorno, Exception):
            raise retorno
        return retorno

    monkeypatch.setattr(gs, "_chamar_api", _fake)


# --- traduzir ---------------------------------------------------------------


def test_traduz_e_devolve_linhas(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    _mock_groq(monkeypatch, json.dumps(["Abra com uma pergunta", "Vá direto ao ponto"]))
    linhas = traducao.traduzir(tipo, "roteiro", _finding_hook(), CFG)
    assert linhas == ["Abra com uma pergunta", "Vá direto ao ponto"]


def test_respeita_top_k(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    _mock_groq(monkeypatch, json.dumps(["a", "b", "c", "d", "e"]))
    linhas = traducao.traduzir(tipo, "roteiro", _finding_hook(), CFG)  # top_k=3
    assert len(linhas) == 3


def test_falha_do_groq_degrada_para_none(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    _mock_groq(monkeypatch, RuntimeError("sem chave"))
    assert traducao.traduzir(tipo, "roteiro", _finding_hook(), CFG) is None


def test_resposta_nao_lista_devolve_none(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    _mock_groq(monkeypatch, json.dumps({"nao": "lista"}))
    assert traducao.traduzir(tipo, "roteiro", _finding_hook(), CFG) is None


def test_identico_ao_bloco_atual_devolve_none(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    # bloco já tem essas linhas ativas
    guia.bloco_de(tipo.assets_dir, "roteiro").substituir(
        [guia.linha("Abra com uma pergunta"), guia.linha("Seja direto")]
    )
    _mock_groq(monkeypatch, json.dumps(["Abra com uma pergunta", "Seja direto"]))
    assert traducao.traduzir(tipo, "roteiro", _finding_hook(), CFG) is None


def test_cap_de_tamanho(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    cfg = mesclar_feedback({"guia": {"top_k": 10, "tamanho_max_chars": 20}})
    _mock_groq(monkeypatch, json.dumps(["linha curta", "outra linha que estoura o cap"]))
    linhas = traducao.traduzir(tipo, "roteiro", _finding_hook(), cfg)
    assert linhas == ["linha curta"]  # a segunda estourou o teto


# --- propor_guia ------------------------------------------------------------


def test_propor_guia_monta_proposta(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    _mock_groq(monkeypatch, json.dumps(["Abra com uma pergunta"]))
    p = traducao.propor_guia(tipo, _finding_hook(), CFG)
    assert p["tipo"] == "guia"
    assert p["bloco"] == "roteiro"
    assert p["pilar"] == "geracao"
    assert p["linhas_novas"] == ["Abra com uma pergunta"]
    assert p["chave"] == "guia:roteiro"


def test_propor_guia_titulo_vai_para_metadados(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    _mock_groq(monkeypatch, json.dumps(["Use números no título"]))
    finding = {**_finding_hook(), "dimensao": "titulo"}
    p = traducao.propor_guia(tipo, finding, CFG)
    assert p["bloco"] == "metadados"
    assert p["pilar"] == "publicacao"


def test_propor_guia_sem_mudanca_none(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    guia.bloco_de(tipo.assets_dir, "roteiro").substituir([guia.linha("Já está aqui")])
    _mock_groq(monkeypatch, json.dumps(["Já está aqui"]))
    assert traducao.propor_guia(tipo, _finding_hook(), CFG) is None


def test_propor_guia_dimensao_nao_textual_none(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    finding = {**_finding_hook(), "dimensao": "fonte"}
    assert traducao.propor_guia(tipo, finding, CFG) is None
