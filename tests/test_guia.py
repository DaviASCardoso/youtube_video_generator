import json

import pytest

from feedback import guia


@pytest.fixture
def assets(tmp_path):
    """Simula tipos/<id>/assets — a pasta guia/ é sua irmã."""
    a = tmp_path / "tipo" / "assets"
    a.mkdir(parents=True)
    return a


def _escrever_bloco(assets, nome, linhas):
    d = assets.parent / "guia"
    d.mkdir(exist_ok=True)
    (d / f"{nome}.json").write_text(
        json.dumps({"versao": 1, "atualizado_em": None, "linhas": linhas}),
        encoding="utf-8",
    )


# --- injeção (compor) -------------------------------------------------------


def test_bloco_ausente_devolve_base_intacto(assets):
    assert guia.compor(assets, "roteiro", "PROMPT BASE") == "PROMPT BASE"


def test_bloco_vazio_devolve_base_intacto(assets):
    _escrever_bloco(assets, "roteiro", [])
    assert guia.compor(assets, "roteiro", "PROMPT BASE") == "PROMPT BASE"


def test_bloco_so_com_vetadas_devolve_base(assets):
    _escrever_bloco(assets, "roteiro", [guia.linha("evite jargão")])
    b = guia.bloco_de(assets, "roteiro")
    b.vetar(0)
    assert guia.compor(assets, "roteiro", "BASE") == "BASE"


def test_injecao_anexa_sob_delimitador(assets):
    _escrever_bloco(assets, "roteiro", [guia.linha("comece com uma pergunta")])
    out = guia.compor(assets, "roteiro", "BASE")
    assert out.startswith("BASE")
    assert guia.DELIMITADOR in out
    assert "- comece com uma pergunta" in out
    # o base fica antes do delimitador, intacto
    assert out.split(guia.DELIMITADOR)[0].strip() == "BASE"


def test_ordena_fixadas_primeiro_depois_confianca(assets):
    _escrever_bloco(assets, "visual", [
        guia.linha("baixa", confianca=0.2),
        guia.linha("alta", confianca=0.9),
        {**guia.linha("fixa", confianca=0.1), "fixado": True},
    ])
    out = guia.compor(assets, "visual", "")
    corpo = out.split(guia.DELIMITADOR)[1]
    ordem = [l for l in corpo.splitlines() if l.startswith("- ")]
    assert ordem == ["- fixa", "- alta", "- baixa"]


def test_base_vazio_so_bloco(assets):
    _escrever_bloco(assets, "fit", [guia.linha("prefira temas concretos")])
    out = guia.compor(assets, "fit", "")
    assert out.startswith(guia.DELIMITADOR)
    assert "- prefira temas concretos" in out


def test_json_corrompido_degrada_para_base(assets):
    d = assets.parent / "guia"
    d.mkdir()
    (d / "roteiro.json").write_text("{ isto não é json", encoding="utf-8")
    assert guia.compor(assets, "roteiro", "BASE") == "BASE"


# --- store (veto/fix/substituir/limpar) -------------------------------------


def test_vetar_e_desvetar(assets):
    _escrever_bloco(assets, "roteiro", [guia.linha("a"), guia.linha("b")])
    b = guia.bloco_de(assets, "roteiro")
    b.vetar(0)
    assert [l["texto"] for l in b.linhas_ativas()] == ["b"]
    b.vetar(0, vetado=False)
    assert {l["texto"] for l in b.linhas_ativas()} == {"a", "b"}


def test_substituir_preserva_veto_por_texto(assets):
    _escrever_bloco(assets, "roteiro", [guia.linha("mantida"), guia.linha("ruim")])
    b = guia.bloco_de(assets, "roteiro")
    b.vetar(1)  # veta "ruim"
    # o LLM reescreve o bloco, ainda incluindo "ruim"
    b.substituir([guia.linha("mantida"), guia.linha("ruim"), guia.linha("nova")])
    ativas = {l["texto"] for l in b.linhas_ativas()}
    assert "ruim" not in ativas  # veto do humano sobreviveu à reescrita
    assert {"mantida", "nova"} <= ativas


def test_substituir_sobe_versao(assets):
    b = guia.bloco_de(assets, "roteiro")
    v1 = b.substituir([guia.linha("x")])["versao"]
    v2 = b.substituir([guia.linha("y")])["versao"]
    assert v2 == v1 + 1


def test_fixar_protege_ordem(assets):
    b = guia.bloco_de(assets, "roteiro")
    b.substituir([guia.linha("baixa", confianca=0.1), guia.linha("alta", confianca=0.9)])
    b.fixar(0)  # fixa "baixa"
    assert b.linhas_ativas()[0]["texto"] == "baixa"


def test_limpar_esvazia(assets):
    b = guia.bloco_de(assets, "roteiro")
    b.substituir([guia.linha("a")])
    b.limpar()
    assert b.linhas_ativas() == []
    assert guia.compor(assets, "roteiro", "BASE") == "BASE"


def test_nomes_conhecidos_cobrem_os_prompts():
    # os 5 slugs injetados nos prompts
    assert set(guia.NOMES) == {"fit", "roteiro", "visual", "metadados", "thumbnail"}
