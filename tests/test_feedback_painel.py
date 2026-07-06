"""Render + ações da página standalone /feedback (fora do TestClient, via env Jinja)."""

from types import SimpleNamespace

from api.templating import templates
from api.routers import feedback as painel_mod
from feedback import guia
from feedback.armazenamento import aplicados_de, findings_de, propostas_de, metricas_de


def _render(tipo):
    ctx = painel_mod._contexto_painel(tipo, SimpleNamespace(session={}))
    return templates.get_template("feedback_painel.html").render(**ctx)


def test_render_vazio(make_tipo):
    html = _render(make_tipo("tipo_teste"))
    assert "Nenhuma proposta pendente" in html
    assert "Guia aprendida" in html


def test_render_com_proposta_e_guia(make_tipo):
    tipo = make_tipo("tipo_teste")
    propostas_de(tipo).adicionar({
        "tipo": "numerico", "alvo": "descoberta.evergreen_ratio",
        "valor_atual": 0.3, "valor_novo": 0.2, "dimensao": "categoria",
        "finding": {"efeito": 8, "metrica": "avg_view_pct", "n": 4},
    })
    guia.bloco_de(tipo.assets_dir, "roteiro").substituir([guia.linha("Abra com pergunta", confianca=0.7)])
    findings_de(tipo).substituir([{"dimensao": "categoria", "valor": "trending", "efeito": 8.0,
                                   "media": 60, "baseline": 52, "n": 4, "confianca": 0.6,
                                   "elegivel": True, "metrica": "avg_view_pct"}], assinatura="x")

    html = _render(tipo)
    assert "descoberta.evergreen_ratio" in html
    assert "Abra com pergunta" in html
    assert "trending" in html


def test_render_performance_com_curva(make_tipo):
    tipo = make_tipo("tipo_teste")
    metricas_de(tipo).gravar_video("vidA", {
        "tema": "Foco", "execucao_id": "e1", "publicado_em": "2026-07-01T14:00:00+00:00",
        "polls": {"72": {"avg_view_pct": 55, "curva": [[0.0, 1.0], [1.0, 0.4]], "marco": 72}},
    })
    # atribuir sem pasta ainda casa métricas (inputs ficam None)
    import feedback.atribuicao as atr
    orig = atr._contexto
    atr._contexto = lambda t: ({}, {}, lambda rec: None)
    try:
        html = _render(tipo)
    finally:
        atr._contexto = orig
    assert "polyline" in html  # a curva virou sparkline SVG


# --- ações ------------------------------------------------------------------


def test_aprovar_via_rota(make_tipo):
    tipo = make_tipo("tipo_teste")
    antigo = tipo.config.get("descoberta.evergreen_ratio")
    reg = propostas_de(tipo).adicionar({"tipo": "numerico", "alvo": "descoberta.evergreen_ratio",
                                        "valor_atual": antigo, "valor_novo": 0.15, "pilar": "descoberta"})
    resp = painel_mod.aprovar_proposta("tipo_teste", reg["id"])
    assert resp.status_code == 303
    from config.tipos import carregar_tipo
    assert carregar_tipo("tipo_teste").config.get("descoberta.evergreen_ratio") == 0.15


def test_vetar_e_limpar_via_rota(make_tipo):
    tipo = make_tipo("tipo_teste")
    guia.bloco_de(tipo.assets_dir, "roteiro").substituir([guia.linha("a"), guia.linha("b")])
    painel_mod.acao_linha("tipo_teste", "roteiro", 0, "vetar")
    ativas = [l["texto"] for l in guia.bloco_de(tipo.assets_dir, "roteiro").linhas_ativas()]
    assert ativas == ["b"]
    painel_mod.limpar_bloco("tipo_teste", "roteiro")
    assert guia.bloco_de(tipo.assets_dir, "roteiro").linhas_ativas() == []


def test_reverter_aplicado_via_rota(make_tipo):
    tipo = make_tipo("tipo_teste")
    antigo = tipo.config.get("descoberta.evergreen_ratio")
    from feedback import aplicacao
    aplicacao.aplicar(tipo, {"tipo": "numerico", "alvo": "descoberta.evergreen_ratio",
                             "valor_novo": 0.9, "valor_atual": antigo})
    painel_mod.reverter_aplicado("tipo_teste", 0)
    from config.tipos import carregar_tipo
    assert carregar_tipo("tipo_teste").config.get("descoberta.evergreen_ratio") == antigo
