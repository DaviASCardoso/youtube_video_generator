import pytest

from feedback import feedback, atribuicao, traducao
from feedback.armazenamento import findings_de, propostas_de
from feedback.configuracao import mesclar_feedback


def _v(vid, avg, **inputs):
    base = {"fonte": None, "categoria": None, "voz": None, "modo_visual": None,
            "hook": None, "titulo": None, "publish_time": None, "duracao": None,
            "thumbnail": None, "fit_score": None}
    base.update(inputs)
    return {"video_id": vid, "tema": vid, "marco": 72, "metricas": {"avg_view_pct": avg},
            "curva": [], "inputs": base}


def _vetores_publish_time():
    # noite performa melhor que manhã, 2 de cada (sample_floor 2)
    return [
        _v("a", 72, publish_time=20), _v("b", 68, publish_time=21),
        _v("c", 40, publish_time=8), _v("d", 44, publish_time=9),
    ]


@pytest.fixture
def tipo_fb(make_tipo):
    cfg = mesclar_feedback({"sample_floor": 2})
    return make_tipo("tipo_teste", config_extra={"feedback": cfg})


# --- sem dados / inerte -----------------------------------------------------


def test_sem_dados_pula(tipo_fb, monkeypatch):
    monkeypatch.setattr(atribuicao, "atribuir", lambda t: [])
    assert feedback.processar(tipo_fb)["pulado"] == "sem_dados"


# --- advisory (default): cria proposta, não muda config ---------------------


def test_advisory_cria_proposta_numerica(tipo_fb, monkeypatch):
    monkeypatch.setattr(atribuicao, "atribuir", lambda t: _vetores_publish_time())
    horario_antes = tipo_fb.config.get("publicacao.timing.horario")

    r = feedback.processar(tipo_fb)
    assert len(r["propostas"]) == 1
    assert r["aplicados"] == []

    pend = propostas_de(tipo_fb).pendentes()
    assert pend[0]["alvo"] == "publicacao.timing.horario"
    # config não mudou (advisory)
    from config.tipos import carregar_tipo
    assert carregar_tipo("tipo_teste").config.get("publicacao.timing.horario") == horario_antes
    # findings guardados para o Controle
    assert findings_de(tipo_fb).itens()


def test_assinatura_inalterada_pula_segunda_passada(tipo_fb, monkeypatch):
    monkeypatch.setattr(atribuicao, "atribuir", lambda t: _vetores_publish_time())
    feedback.processar(tipo_fb)
    r2 = feedback.processar(tipo_fb)
    assert r2["pulado"] == "inalterado"


def test_nao_duplica_proposta_para_mesmo_alvo(tipo_fb, monkeypatch):
    monkeypatch.setattr(atribuicao, "atribuir", lambda t: _vetores_publish_time())
    feedback.processar(tipo_fb)  # cria a proposta de horário
    # inputs mudam (assinatura nova) mas o vencedor é o mesmo alvo
    outros = _vetores_publish_time() + [_v("e", 90, publish_time=22)]
    monkeypatch.setattr(atribuicao, "atribuir", lambda t: outros)
    feedback.processar(tipo_fb)
    alvos = [p["alvo"] for p in propostas_de(tipo_fb).pendentes()]
    assert alvos.count("publicacao.timing.horario") == 1  # não duplicou


# --- auto: aplica na hora ---------------------------------------------------


def test_auto_aplica_ajuste(make_tipo, monkeypatch):
    cfg = mesclar_feedback({"sample_floor": 2, "aplicacao": {"publicacao": "auto"}})
    tipo = make_tipo("tipo_teste", config_extra={"feedback": cfg})
    monkeypatch.setattr(atribuicao, "atribuir", lambda t: _vetores_publish_time())

    r = feedback.processar(tipo)
    assert len(r["aplicados"]) == 1
    assert r["propostas"] == []
    from config.tipos import carregar_tipo
    # 18:00 rumo a 20:00, limitado a 30min => 18:30
    assert carregar_tipo("tipo_teste").config.get("publicacao.timing.horario") == "18:30"


# --- guia (textual) via tradução mockada ------------------------------------


def test_guia_textual_cria_proposta(tipo_fb, monkeypatch):
    vetores = [
        _v("a", 80, hook="Você acha que precisa de disciplina?"),
        _v("b", 78, hook="A verdade incomoda"),
        _v("c", 20, hook="Hoje falo sobre produtividade"),
        _v("d", 15, hook="Mais um roteiro morno"),
    ]
    monkeypatch.setattr(atribuicao, "atribuir", lambda t: vetores)
    monkeypatch.setattr(
        traducao, "propor_guia",
        lambda tipo, finding, cfg: {"tipo": "guia", "pilar": "geracao", "alvo": "guia:roteiro",
                                    "bloco": "roteiro", "dimensao": "hook",
                                    "linhas_novas": ["Abra com pergunta"], "chave": "guia:roteiro"},
    )
    r = feedback.processar(tipo_fb)
    ids = [p for p in propostas_de(tipo_fb).pendentes() if p["tipo"] == "guia"]
    assert ids and ids[0]["bloco"] == "roteiro"
    assert len(r["propostas"]) >= 1
