from geracao import custo
from geracao.custo import GastoDiario, Ledger, checar_orcamento, custo_tts


def test_custo_tts_por_char():
    assert custo_tts("abcd") == 4 * custo.CUSTO_TTS_POR_CHAR


def test_ledger_acumula():
    led = Ledger()
    led.registrar("roteiro", "groq", 0.0005)
    led.registrar("visuais", "flux", 0.04)
    led.registrar("visuais", "flux", 0.02)
    assert abs(led.total() - 0.0605) < 1e-9
    assert led.por_estagio()["visuais"] == 0.06
    assert led.provedores()["roteiro"] == "groq"
    assert len(led.itens()) == 3


def test_gasto_diario_acumula_por_dia(tmp_path):
    g = GastoDiario(tmp_path / "custo.json")
    assert g.gasto_hoje() == 0.0
    g.registrar(0.10)
    g.registrar(0.05)
    assert abs(g.gasto_hoje() - 0.15) < 1e-9


def test_gasto_diario_ignora_json_corrompido(tmp_path):
    caminho = tmp_path / "custo.json"
    caminho.write_text("{ nao é json", encoding="utf-8")
    g = GastoDiario(caminho)
    assert g.gasto_hoje() == 0.0  # degrada em vez de quebrar


_CFG = {"por_video_usd": 1.0, "por_dia_usd": 10.0, "acao": "degradar"}


def test_checar_orcamento_ok():
    assert checar_orcamento(0.2, 0.3, 1.0, _CFG) == "ok"


def test_checar_orcamento_estoura_video():
    assert checar_orcamento(0.9, 0.3, 0.0, _CFG) == "degradar"


def test_checar_orcamento_estoura_dia():
    assert checar_orcamento(0.1, 0.3, 9.9, _CFG) == "degradar"


def test_checar_orcamento_acao_parar():
    cfg = {**_CFG, "acao": "parar"}
    assert checar_orcamento(0.9, 0.3, 0.0, cfg) == "parar"


def test_checar_orcamento_teto_zero_e_sem_limite():
    cfg = {"por_video_usd": 0.0, "por_dia_usd": 0.0, "acao": "parar"}
    assert checar_orcamento(999.0, 999.0, 999.0, cfg) == "ok"
