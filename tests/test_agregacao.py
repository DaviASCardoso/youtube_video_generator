from feedback import agregacao
from feedback.configuracao import mesclar_feedback

CFG = mesclar_feedback({"sample_floor": 2})


def _v(video_id, avg, **inputs):
    base = {"fonte": None, "categoria": None, "voz": None, "modo_visual": None,
            "hook": None, "titulo": None, "publish_time": None, "duracao": None,
            "thumbnail": None, "fit_score": None}
    base.update(inputs)
    return {"video_id": video_id, "metricas": {"avg_view_pct": avg}, "curva": [], "inputs": base}


# --- categórico -------------------------------------------------------------


def test_categorico_efeito_vs_baseline():
    vetores = [
        _v("a", 60, fonte="reddit"),
        _v("b", 50, fonte="reddit"),
        _v("c", 30, fonte="pool"),
        _v("d", 40, fonte="pool"),
    ]
    findings = agregacao.agregar(vetores, CFG)
    reddit = next(f for f in findings if f["dimensao"] == "fonte" and f["valor"] == "reddit")
    assert reddit["media"] == 55.0
    assert reddit["baseline"] == 45.0
    assert reddit["efeito"] == 10.0
    assert reddit["n"] == 2
    assert reddit["elegivel"] is True
    assert reddit["metrica"] == "avg_view_pct"


def test_piso_amostral_bloqueia_elegibilidade():
    vetores = [_v("a", 90, fonte="reddit"), _v("b", 10, fonte="pool"), _v("c", 20, fonte="pool")]
    findings = agregacao.agregar(vetores, CFG)
    reddit = next(f for f in findings if f["valor"] == "reddit")
    assert reddit["n"] == 1
    assert reddit["elegivel"] is False  # n < sample_floor(2)


def test_confianca_cresce_com_n():
    poucos = [_v(str(i), 50, fonte="reddit") for i in range(2)]
    muitos = [_v(str(i), 50, fonte="reddit") for i in range(10)]
    f_poucos = next(f for f in agregacao.agregar(poucos, CFG) if f["valor"] == "reddit")
    f_muitos = next(f for f in agregacao.agregar(muitos, CFG) if f["valor"] == "reddit")
    assert f_muitos["confianca"] > f_poucos["confianca"]


def test_valor_none_e_ignorado():
    vetores = [_v("a", 50, fonte=None), _v("b", 60, fonte="reddit")]
    findings = agregacao.agregar(vetores, CFG)
    fontes = [f["valor"] for f in findings if f["dimensao"] == "fonte"]
    assert fontes == ["reddit"]


# --- numérico (buckets) -----------------------------------------------------


def test_publish_time_bucketiza():
    vetores = [
        _v("a", 70, publish_time=19), _v("b", 65, publish_time=20),  # noite
        _v("c", 40, publish_time=8), _v("d", 45, publish_time=9),   # manha
    ]
    findings = agregacao.agregar(vetores, CFG)
    noite = next(f for f in findings if f["dimensao"] == "publish_time" and f["valor"] == "noite")
    assert noite["tipo"] == "numerico"
    assert noite["media"] == 67.5
    assert noite["efeito"] > 0


def test_duracao_buckets():
    assert agregacao._bucket("duracao", 20) == "curto"
    assert agregacao._bucket("duracao", 45) == "medio"
    assert agregacao._bucket("duracao", 90) == "longo"


def test_fit_score_buckets():
    assert agregacao._bucket("fit_score", 50) == "baixo"
    assert agregacao._bucket("fit_score", 70) == "medio"
    assert agregacao._bucket("fit_score", 90) == "alto"


# --- textual ----------------------------------------------------------------


def test_textual_carrega_exemplos_dos_melhores():
    vetores = [
        _v("a", 80, hook="Você acha que precisa de disciplina?"),
        _v("b", 70, hook="A verdade é desconfortável"),
        _v("c", 20, hook="Hoje vou falar sobre produtividade"),
    ]
    findings = agregacao.agregar(vetores, CFG)
    hook = next(f for f in findings if f["dimensao"] == "hook")
    assert hook["tipo"] == "textual"
    assert hook["valor"] is None
    assert hook["exemplos"][0] == "Você acha que precisa de disciplina?"  # melhor primeiro
    assert hook["n"] == 3
    assert hook["elegivel"] is True


def test_textual_sem_texto_nao_gera_finding():
    vetores = [_v("a", 50, hook=None), _v("b", 60, hook=None)]
    findings = agregacao.agregar(vetores, CFG)
    assert not any(f["dimensao"] == "hook" for f in findings)


# --- ordenação e assinatura -------------------------------------------------


def test_ordena_mais_forte_primeiro():
    vetores = [
        _v("a", 90, fonte="reddit", categoria="trending"),
        _v("b", 88, fonte="reddit", categoria="trending"),
        _v("c", 12, fonte="pool", categoria="evergreen"),
        _v("d", 10, fonte="pool", categoria="evergreen"),
    ]
    findings = agregacao.agregar(vetores, CFG)
    # o primeiro finding é elegível e de maior efeito absoluto
    assert findings[0]["elegivel"] is True
    assert abs(findings[0]["efeito"]) >= abs(findings[-1]["efeito"])


def test_sem_amostras_devolve_vazio():
    assert agregacao.agregar([], CFG) == []
    # métrica ausente em todos
    v = [{"video_id": "a", "metricas": {}, "inputs": {"fonte": "reddit"}}]
    assert agregacao.agregar(v, CFG) == []


def test_assinatura_estavel_e_sensivel():
    v1 = [_v("a", 50, fonte="reddit"), _v("b", 60, fonte="pool")]
    v1[0]["marco"] = 24
    v1[1]["marco"] = 24
    a1 = agregacao.assinatura(v1)
    assert a1 == agregacao.assinatura(list(reversed(v1)))  # ordem-independente
    v2 = [dict(v1[0], metricas={"avg_view_pct": 99}), v1[1]]
    assert agregacao.assinatura(v2) != a1  # métrica mudou
