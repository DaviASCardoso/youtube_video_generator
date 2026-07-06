"""Roteamento determinístico: dimensão → destino (config numérico ou guia de prompt).

Um **mapa estático** (não um palpite de LLM) decide onde cada finding vai. Dimensões
numéricas viram **ajustes limitados** no config do pilar-alvo; dimensões categóricas
viram **set-value** reversível (troca de default); dimensões textuais viram **guia de
prompt** (a tradução por LLM é feita em `traducao`, nunca aqui). Dimensões sem knob
real (ex.: `fonte`, `fit_score`) não têm rota — ficam só como finding exibido.

`propor(finding, tipo, cfg)` produz uma proposta **concreta e limitada** (valor novo já
calculado e dentro do teto por aplicação) ou `None` quando não há mudança a fazer. A
aplicação (advisory/auto) e a reversão são de `aplicacao`.
"""

# Mapa estático de rotas. `classe`: numerico | set | guia. `pilar`: o alvo do gate
# advisory/auto (descoberta/geracao/publicacao).
ROTAS = {
    "publish_time": {
        "classe": "numerico", "pilar": "publicacao", "alvo": "publicacao.timing.horario",
        "unidade": "horario",
        "representativo": {"madrugada": "03:00", "manha": "09:00", "tarde": "15:00", "noite": "20:00"},
    },
    "duracao": {
        "classe": "numerico", "pilar": "geracao", "alvo": "geracao.roteiro.duracao_alvo_seg",
        "unidade": "segundos", "lim": (5, 3600),
        "representativo": {"curto": 20, "medio": 45, "longo": 90},
    },
    "categoria": {
        "classe": "numerico", "pilar": "descoberta", "alvo": "descoberta.evergreen_ratio",
        "unidade": "fracao", "lim": (0.0, 1.0),
        # trending performando melhor ⇒ menos evergreen; evergreen melhor ⇒ mais.
        "direcao": {"trending": -1, "evergreen": +1},
    },
    "voz": {"classe": "set", "pilar": "geracao", "alvo": "tts.voz"},
    "modo_visual": {"classe": "set", "pilar": "geracao", "alvo": "imagens.modo"},
    "thumbnail": {"classe": "set", "pilar": "publicacao", "alvo": "publicacao.thumbnail.ativo", "booleano": True},
    "hook": {"classe": "guia", "pilar": "geracao", "bloco": "roteiro"},
    "titulo": {"classe": "guia", "pilar": "publicacao", "bloco": "metadados"},
}


def classificar(dimensao: str) -> dict | None:
    """A rota de uma dimensão, ou None se ela não é ajustável."""
    return ROTAS.get(dimensao)


def melhores_por_dimensao(findings: list[dict]) -> list[dict]:
    """Por dimensão, o finding elegível vencedor (maior média, efeito positivo).

    Evita propor em cima de cada valor; roteia só o melhor de cada dimensão.
    """
    melhor: dict[str, dict] = {}
    for f in findings:
        if not f.get("elegivel") or f.get("efeito", 0) <= 0:
            continue
        dim = f["dimensao"]
        if dim not in ROTAS:
            continue
        atual = melhor.get(dim)
        if atual is None or f["media"] > atual["media"]:
            melhor[dim] = f
    return list(melhor.values())


# --- cálculo do valor novo (limitado) ---------------------------------------


def _hhmm_para_min(hhmm: str) -> int:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _min_para_hhmm(minutos: int) -> str:
    minutos = int(minutos) % (24 * 60)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _mover_horario(atual: str, alvo: str, max_delta_min: int) -> str:
    a, b = _hhmm_para_min(atual), _hhmm_para_min(alvo)
    diff = b - a
    passo = max(-max_delta_min, min(max_delta_min, diff))
    return _min_para_hhmm(a + passo)


def _mover_numero(atual: float, alvo: float, max_delta: float, lim) -> float:
    diff = alvo - atual
    passo = max(-max_delta, min(max_delta, diff))
    novo = atual + passo
    lo, hi = lim
    return max(lo, min(hi, novo))


def propor(finding: dict, tipo, cfg: dict) -> dict | None:
    """Proposta concreta e limitada para um finding vencedor, ou None se sem mudança.

    Só numérico/set: as propostas de guia (textuais) são construídas via `traducao`.
    """
    rota = ROTAS.get(finding["dimensao"])
    if rota is None or rota["classe"] == "guia":
        return None

    caps = cfg.get("caps_numericos", {})
    max_frac = float(caps.get("max_delta_frac", 0.1))
    max_min = int(caps.get("max_delta_min", 30))

    try:
        atual = tipo.config.get(rota["alvo"])
    except Exception:  # noqa: BLE001
        atual = None

    if rota["classe"] == "set":
        novo = finding["valor"]
        if rota.get("booleano"):
            novo = str(finding["valor"]).lower() in ("true", "1", "sim")
        if novo == atual:
            return None
        return _montar(finding, rota, atual, novo,
                       f"Definir {rota['alvo']} = {novo!r} (melhor: {finding['valor']!r}).")

    # numérico
    unidade = rota["unidade"]
    if unidade == "horario":
        alvo_val = rota["representativo"].get(finding["valor"])
        if not alvo_val:
            return None
        novo = _mover_horario(str(atual or "18:00"), alvo_val, max_min)
    elif unidade == "fracao":
        atual = float(atual if atual is not None else 0.5)
        sinal = rota["direcao"].get(finding["valor"], 0)
        if sinal == 0:
            return None
        novo = _mover_numero(atual, atual + sinal, max_frac, rota["lim"])
        novo = round(novo, 4)
    elif unidade == "segundos":
        atual = float(atual if atual is not None else 60)
        alvo_val = rota["representativo"].get(finding["valor"])
        if alvo_val is None:
            return None
        novo = _mover_numero(atual, alvo_val, max_frac * atual, rota["lim"])
        novo = int(round(novo))
    else:
        return None

    if novo == atual:
        return None
    return _montar(finding, rota, atual, novo,
                   f"Ajustar {rota['alvo']}: {atual} → {novo} (melhor faixa: {finding['valor']}).")


def _montar(finding, rota, atual, novo, descricao) -> dict:
    return {
        "tipo": "numerico" if rota["classe"] == "numerico" else "set",
        "pilar": rota["pilar"],
        "alvo": rota["alvo"],
        "dimensao": finding["dimensao"],
        "valor_atual": atual,
        "valor_novo": novo,
        "descricao": descricao,
        "chave": rota["alvo"],  # idempotência: uma proposta pendente por alvo
        "finding": {
            "dimensao": finding["dimensao"], "valor": finding.get("valor"),
            "efeito": finding.get("efeito"), "n": finding.get("n"),
            "confianca": finding.get("confianca"), "metrica": finding.get("metrica"),
        },
    }
