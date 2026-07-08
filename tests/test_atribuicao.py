import json

import pytest

from feedback import atribuicao
from feedback.armazenamento import metricas_de


@pytest.fixture
def pasta_run(tmp_path):
    """Uma pasta de run com sidecar.json + publicacao.json."""
    p = tmp_path / "run1"
    p.mkdir()
    (p / "sidecar.json").write_text(json.dumps({
        "tema": "Foco no essencial",
        "roteiro": "Você acha que precisa de mais uma técnica?\nMas o problema é outro.",
        "duracao_seg": 45.0,
        "provedores": {"visuais": "visuais_pexels", "narracao": "narracao_google"},
    }), encoding="utf-8")
    (p / "publicacao.json").write_text(json.dumps({
        "metadados": {"titulo": "A verdade sobre foco", "tags": ["foco"]},
        "thumbnail": {"texto": "FOCO"},
    }), encoding="utf-8")
    return p


def _ctx(pasta, decidido=None, exec_id="e1"):
    decididos = {}
    if decidido:
        from descoberta.tendencias import _normalizar
        decididos[_normalizar(decidido["tema"])] = decidido
    execucoes = {exec_id: {"id": exec_id, "output_path": str(pasta / "video_final.mp4")}}
    return decididos, execucoes, lambda rec: pasta


def _registro():
    return {
        "id": "vidA",
        "tema": "Foco no essencial",
        "execucao_id": "e1",
        "publicado_em": "2026-07-01T14:00:00+00:00",
        "polls": {
            "24": {"avg_view_pct": 40, "views": 500, "curva": [[0.0, 1.0]], "marco": 24},
            "72": {"avg_view_pct": 55, "views": 1200, "curva": [[0.0, 1.0], [1.0, 0.5]], "marco": 72},
        },
    }


# --- maduras ----------------------------------------------------------------


def test_maduras_pega_maior_marco():
    metricas, curva, marco = atribuicao.maduras(_registro())
    assert marco == 72
    assert metricas == {"avg_view_pct": 55, "views": 1200}
    assert curva == [[0.0, 1.0], [1.0, 0.5]]


def test_maduras_sem_polls():
    assert atribuicao.maduras({"polls": {}}) == ({}, [], None)


# --- inputs_de --------------------------------------------------------------


def test_inputs_completos(make_tipo, pasta_run):
    tipo = make_tipo("tipo_teste")  # tts.voz = "v", imagens.modo personagem
    decidido = {"tema": "Foco no essencial", "fonte": "reddit", "categoria": "trending", "fit_score": 82}
    ctx = _ctx(pasta_run, decidido)
    inputs = atribuicao.inputs_de(tipo, _registro(), ctx)
    assert inputs["fonte"] == "reddit"
    assert inputs["categoria"] == "trending"
    assert inputs["fit_score"] == 82
    assert inputs["voz"] == "v"
    assert inputs["modo_visual"] == "pexels"  # deduzido dos provedores (fonte do fundo)
    assert inputs["hook"] == "Você acha que precisa de mais uma técnica?"
    assert inputs["titulo"] == "A verdade sobre foco"
    assert inputs["publish_time"] == 14
    assert inputs["duracao"] == 45.0
    assert inputs["thumbnail"] is True


def test_inputs_tema_sem_decisao_degrada(make_tipo, pasta_run):
    tipo = make_tipo("tipo_teste")
    ctx = _ctx(pasta_run, decidido=None)
    inputs = atribuicao.inputs_de(tipo, _registro(), ctx)
    assert inputs["fonte"] is None
    assert inputs["categoria"] is None
    # mas o que vem do sidecar/pub segue disponível
    assert inputs["titulo"] == "A verdade sobre foco"


def test_inputs_sem_pasta_degrada(make_tipo):
    tipo = make_tipo("tipo_teste")
    ctx = ({}, {}, lambda rec: None)  # execução não encontrada
    inputs = atribuicao.inputs_de(tipo, _registro(), ctx)
    assert inputs["hook"] is None
    assert inputs["titulo"] is None
    assert inputs["thumbnail"] is False
    assert inputs["publish_time"] == 14  # este vem do registro de métricas, não da pasta


def test_modo_visual_flux_vira_ia(make_tipo, tmp_path):
    tipo = make_tipo("tipo_teste")
    p = tmp_path / "r"
    p.mkdir()
    (p / "sidecar.json").write_text(json.dumps({"provedores": {"visuais": "visuais_flux"}}), encoding="utf-8")
    ctx = ({}, {"e1": {"id": "e1"}}, lambda rec: p)
    inputs = atribuicao.inputs_de(tipo, _registro(), ctx)
    assert inputs["modo_visual"] == "ia"


def test_modo_visual_e_hook_explicitos_do_sidecar(make_tipo, tmp_path):
    # Quando a Geração grava as chaves, a atribuição as usa direto (não deduz).
    tipo = make_tipo("tipo_teste")
    p = tmp_path / "r"
    p.mkdir()
    (p / "sidecar.json").write_text(json.dumps({
        "modo_visual": "pexels",
        "hook": "Uma abertura explícita.",
        "roteiro": "linha ignorada\noutra",
        "provedores": {"visuais": "visuais_flux"},  # ignorado: modo_visual é explícito
    }), encoding="utf-8")
    ctx = ({}, {"e1": {"id": "e1"}}, lambda rec: p)
    inputs = atribuicao.inputs_de(tipo, _registro(), ctx)
    assert inputs["modo_visual"] == "pexels"
    assert inputs["hook"] == "Uma abertura explícita."


# --- atribuir (end-to-end com mocks) ----------------------------------------


def test_atribuir_junta_metricas_e_inputs(make_tipo, pasta_run, monkeypatch):
    tipo = make_tipo("tipo_teste")
    metricas_de(tipo).gravar_video("vidA", _registro())
    decidido = {"tema": "Foco no essencial", "fonte": "reddit", "categoria": "trending", "fit_score": 82}
    monkeypatch.setattr(atribuicao, "_contexto", lambda t: _ctx(pasta_run, decidido))

    vetores = atribuicao.atribuir(tipo)
    assert len(vetores) == 1
    v = vetores[0]
    assert v["video_id"] == "vidA"
    assert v["metricas"]["avg_view_pct"] == 55
    assert v["inputs"]["fonte"] == "reddit"
    assert v["marco"] == 72


def test_atribuir_ignora_video_sem_dado_maduro(make_tipo, monkeypatch):
    tipo = make_tipo("tipo_teste")
    metricas_de(tipo).gravar_video("vazio", {"tema": "x", "polls": {}})
    monkeypatch.setattr(atribuicao, "_contexto", lambda t: ({}, {}, lambda rec: None))
    assert atribuicao.atribuir(tipo) == []
