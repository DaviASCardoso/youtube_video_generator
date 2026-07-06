from feedback import roteador
from feedback.configuracao import mesclar_feedback

CFG = mesclar_feedback({"caps_numericos": {"max_delta_frac": 0.1, "max_delta_min": 30}})


def _f(dimensao, valor, media=60, efeito=10, elegivel=True):
    return {"dimensao": dimensao, "valor": valor, "media": media, "efeito": efeito,
            "n": 5, "confianca": 0.6, "elegivel": elegivel, "metrica": "avg_view_pct"}


# --- classificação ----------------------------------------------------------


def test_dimensao_sem_knob_nao_tem_rota():
    assert roteador.classificar("fonte") is None
    assert roteador.classificar("fit_score") is None


def test_dimensoes_conhecidas_tem_classe():
    assert roteador.classificar("publish_time")["classe"] == "numerico"
    assert roteador.classificar("voz")["classe"] == "set"
    assert roteador.classificar("hook")["classe"] == "guia"


# --- melhores por dimensão --------------------------------------------------


def test_melhores_pega_vencedor_elegivel():
    findings = [
        _f("publish_time", "noite", media=70),
        _f("publish_time", "manha", media=40, efeito=-5),
        _f("fonte", "reddit"),  # sem rota
        _f("categoria", "trending", elegivel=False),  # não elegível
    ]
    melhores = roteador.melhores_por_dimensao(findings)
    dims = {f["dimensao"] for f in melhores}
    assert dims == {"publish_time"}
    assert melhores[0]["valor"] == "noite"


# --- proposta numérica (horário) --------------------------------------------


def test_horario_move_limitado(make_tipo):
    tipo = make_tipo("tipo_teste")  # agendamento 06:00; publicacao.timing.horario 18:00
    p = roteador.propor(_f("publish_time", "noite"), tipo, CFG)  # alvo 20:00
    assert p["tipo"] == "numerico"
    assert p["alvo"] == "publicacao.timing.horario"
    # de 18:00 rumo a 20:00, mas limitado a 30 min => 18:30
    assert p["valor_novo"] == "18:30"
    assert p["chave"] == "publicacao.timing.horario"


def test_horario_ja_no_alvo_sem_proposta(make_tipo):
    from publicacao.configuracao import mesclar_publicacao
    pub = mesclar_publicacao({"timing": {"horario": "20:00"}})
    tipo = make_tipo("tipo_teste", config_extra={"publicacao": pub})
    assert roteador.propor(_f("publish_time", "noite"), tipo, CFG) is None


# --- proposta numérica (fração: evergreen_ratio) ----------------------------


def test_categoria_trending_baixa_evergreen(make_tipo):
    tipo = make_tipo("tipo_teste")
    p = roteador.propor(_f("categoria", "trending"), tipo, CFG)
    atual = tipo.config.get("descoberta.evergreen_ratio")
    assert p["valor_novo"] < atual  # trending melhor => menos evergreen
    assert p["valor_novo"] >= 0.0


def test_categoria_evergreen_sobe_evergreen(make_tipo):
    tipo = make_tipo("tipo_teste")
    p = roteador.propor(_f("categoria", "evergreen"), tipo, CFG)
    atual = tipo.config.get("descoberta.evergreen_ratio")
    assert p["valor_novo"] > atual


# --- proposta numérica (segundos) -------------------------------------------


def test_duracao_move_fracionado(make_tipo):
    tipo = make_tipo("tipo_teste")
    alvo = tipo.config.get("geracao.roteiro.duracao_alvo_seg")
    p = roteador.propor(_f("duracao", "longo"), tipo, CFG)  # alvo 90s
    if alvo < 90:
        assert p["valor_novo"] > alvo
        assert p["valor_novo"] <= alvo + max(1, round(0.1 * alvo)) + 1  # limitado à fração


# --- proposta set (categórico) ----------------------------------------------


def test_set_troca_valor(make_tipo):
    tipo = make_tipo("tipo_teste")  # imagens.modo = personagem
    p = roteador.propor(_f("modo_visual", "ia"), tipo, CFG)
    assert p["tipo"] == "set"
    assert p["alvo"] == "imagens.modo"
    assert p["valor_novo"] == "ia"
    assert p["valor_atual"] == "personagem"


def test_set_igual_ao_atual_sem_proposta(make_tipo):
    tipo = make_tipo("tipo_teste")  # imagens.modo = personagem
    assert roteador.propor(_f("modo_visual", "personagem"), tipo, CFG) is None


def test_thumbnail_booleano(make_tipo):
    tipo = make_tipo("tipo_teste")  # thumbnail.ativo = False por default
    p = roteador.propor(_f("thumbnail", "True"), tipo, CFG)
    assert p["valor_novo"] is True
    assert p["alvo"] == "publicacao.thumbnail.ativo"


def test_guia_nao_gera_proposta_numerica(make_tipo):
    tipo = make_tipo("tipo_teste")
    assert roteador.propor(_f("hook", None), tipo, CFG) is None
