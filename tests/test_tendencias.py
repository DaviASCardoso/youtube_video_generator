from descoberta.tendencias import (
    HistoricoTendencias,
    _default_prompt_tendencia,
    _normalizar,
    _prompt_do_tipo,
)


# --- parte pura / armazenamento ---

def test_normalizar_colapsa_espacos_e_minusculas():
    assert _normalizar("  Project   Hail  MARY ") == "project hail mary"


def test_historico_registrar_e_recentes(tmp_path):
    h = HistoricoTendencias(tmp_path / "hist.json")
    h.registrar("canal", "Trend X", "Google Trends", "Tema gerado")
    recentes = h.trends_recentes("canal", dias=14)
    assert "trend x" in recentes  # normalizado
    # isolamento por tipo
    assert h.trends_recentes("outro", dias=14) == set()


def test_historico_recentes_respeita_janela(tmp_path):
    from datetime import datetime, timedelta, timezone

    h = HistoricoTendencias(tmp_path / "hist.json")
    h.registrar("canal", "Antiga", "f", "t")
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


def test_prompt_do_tipo_le_arquivo(make_tipo):
    tipo = make_tipo()
    (tipo.assets_dir / "system_prompt_tendencia.txt").write_text(
        "critério do canal", encoding="utf-8"
    )
    assert _prompt_do_tipo(tipo) == "critério do canal"
