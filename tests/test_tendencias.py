import pytest

from scripts import tendencias
from scripts.tendencias import (
    HistoricoTendencias,
    _default_prompt_tendencia,
    _escolher_tendencia,
    _normalizar,
    _prompt_do_tipo,
    coletar_temas_do_dia,
)
from scripts.gemini import TemaTendencia


# --- parte pura / armazenamento ---

def test_normalizar_colapsa_espacos_e_minusculas():
    assert _normalizar("  Project   Hail  MARY ") == "project hail mary"


def test_escolher_tendencia_pula_recentes():
    nomes = ["A", "B", "C"]
    recentes = {"a", "b"}
    assert _escolher_tendencia(nomes, recentes) == "C"


def test_escolher_tendencia_todas_repetidas():
    assert _escolher_tendencia(["A"], {"a"}) is None


def test_historico_registrar_e_recentes(tmp_path):
    h = HistoricoTendencias(tmp_path / "hist.json")
    h.registrar("canal", "Trend X", "Google Trends", "Tema gerado")
    recentes = h.trends_recentes("canal", dias=14)
    assert "trend x" in recentes  # normalizado
    # isolamento por tipo
    assert h.trends_recentes("outro", dias=14) == set()


def test_historico_recentes_respeita_janela(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    h = HistoricoTendencias(tmp_path / "hist.json")
    reg = h.registrar("canal", "Antiga", "f", "t")
    # reescreve a data para 30 dias atrás
    dados = h.listar()
    dados[0]["escolhido_em"] = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()
    h._salvar(dados)
    assert h.trends_recentes("canal", dias=14) == set()  # fora da janela


def test_prompt_do_tipo_usa_default_sem_arquivo(make_tipo):
    tipo = make_tipo()
    assert _prompt_do_tipo(tipo) == _default_prompt_tendencia()


# --- orquestração ---

@pytest.fixture
def hist_temp(tmp_path, monkeypatch):
    h = HistoricoTendencias(tmp_path / "tend_hist.json")
    monkeypatch.setattr(tendencias, "historico_tendencias", h)
    return h


def test_coletar_desativado_nao_faz_nada(sistema_temp, monkeypatch):
    sistema_temp._config["tendencias"]["ativo"] = False
    resumo = coletar_temas_do_dia()
    assert resumo == {"ativo": False, "tipos": []}


def test_coletar_sem_tendencias_pula(sistema_temp, hist_temp, monkeypatch):
    monkeypatch.setattr(tendencias.trends, "buscar_tendencias", lambda **k: [])
    monkeypatch.setattr(tendencias, "listar_tipos_ativos", lambda: [])
    resumo = coletar_temas_do_dia()
    assert resumo["erro"] == "sem tendências"


def test_coletar_adiciona_tema_e_registra(sistema_temp, hist_temp, make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(
        tendencias.trends, "buscar_tendencias", lambda **k: ["Trend Nova"]
    )
    monkeypatch.setattr(tendencias, "listar_tipos_ativos", lambda: [tipo])
    monkeypatch.setattr(
        tendencias.gemini,
        "gerar_tema_de_tendencia",
        lambda tend, prompt: TemaTendencia(tema="Tema do Canal", justificativa="j"),
    )

    resumo = coletar_temas_do_dia()
    assert resumo["tipos"][0]["status"] == "ok"
    # tema entrou na fila com fonte trends e prioridade configurada
    fila = tipo.temas.listar()
    assert fila[0]["tema"] == "Tema do Canal"
    assert fila[0]["fonte"] == "trends"
    assert fila[0]["prioridade"] == 60
    # a tendência crua foi registrada para o dedupe futuro
    assert "trend nova" in hist_temp.trends_recentes(tipo.id, dias=14)


def test_coletar_pula_tendencia_ja_usada(sistema_temp, hist_temp, make_tipo, monkeypatch):
    tipo = make_tipo()
    hist_temp.registrar(tipo.id, "Trend Velha", "Google Trends", "tema antigo")
    monkeypatch.setattr(
        tendencias.trends, "buscar_tendencias", lambda **k: ["Trend Velha", "Trend Fresca"]
    )
    monkeypatch.setattr(tendencias, "listar_tipos_ativos", lambda: [tipo])
    capturadas = []
    monkeypatch.setattr(
        tendencias.gemini,
        "gerar_tema_de_tendencia",
        lambda tend, prompt: capturadas.append(tend)
        or TemaTendencia(tema="T", justificativa="j"),
    )

    coletar_temas_do_dia()
    # deve ter escolhido a fresca, não a já usada
    assert capturadas == ["Trend Fresca"]


def test_coletar_dry_run_nao_escreve(sistema_temp, hist_temp, make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(tendencias.trends, "buscar_tendencias", lambda **k: ["Trend"])
    monkeypatch.setattr(tendencias, "listar_tipos_ativos", lambda: [tipo])
    monkeypatch.setattr(
        tendencias.gemini,
        "gerar_tema_de_tendencia",
        lambda tend, prompt: TemaTendencia(tema="T", justificativa="j"),
    )

    coletar_temas_do_dia(dry_run=True)
    assert tipo.temas.total() == 0  # nada na fila
    assert hist_temp.trends_recentes(tipo.id, dias=14) == set()  # nada registrado
