"""Agregação: rola as métricas por dimensão de input em findings.

Recebe os vetores da atribuição e produz **findings** estruturados (dimensão, valor,
efeito vs. baseline, tamanho de amostra, confiança). É **ciente do tamanho de amostra**:
uma dimensão/valor só é elegível (pode virar vencedor/perdedor e ser roteada) quando
tem pelo menos `sample_floor` vídeos atrás — nunca super-ajusta num vídeo de sorte.

Três famílias de dimensão:
- **categóricas** (fonte, categoria, voz, modo_visual, thumbnail): agrupa por valor.
- **numéricas** (publish_time, duracao, fit_score): agrupa por faixa (bucket) — a rota
  numérica ajusta o config na direção da melhor faixa.
- **textuais** (hook, titulo): não há valor a agrupar; o finding carrega os exemplos que
  performaram melhor, para o tradutor virar guia de prompt.

`assinatura(vetores)` dá um hash dos inputs do cálculo — o orquestrador usa para não
recomputar um agregado cujos inputs não mudaram.
"""

import hashlib
import json

DIMENSOES_CATEGORICAS = ("fonte", "categoria", "voz", "modo_visual", "thumbnail")
DIMENSOES_NUMERICAS = ("publish_time", "duracao", "fit_score")
DIMENSOES_TEXTUAIS = ("hook", "titulo")

# Nº de exemplos textuais (melhores performers) que um finding textual carrega.
_TOP_EXEMPLOS = 3


def _bucket(dimensao: str, valor) -> str | None:
    """Faixa de uma dimensão numérica (rótulo estável)."""
    if valor is None:
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if dimensao == "publish_time":
        if v < 6:
            return "madrugada"
        if v < 12:
            return "manha"
        if v < 18:
            return "tarde"
        return "noite"
    if dimensao == "duracao":
        if v < 30:
            return "curto"
        if v <= 60:
            return "medio"
        return "longo"
    if dimensao == "fit_score":
        if v < 60:
            return "baixo"
        if v <= 80:
            return "medio"
        return "alto"
    return str(valor)


def _confianca(n: int, floor: int) -> float:
    """Confiança encolhida pelo tamanho de amostra: n/(n+floor), em [0,1)."""
    floor = max(1, int(floor))
    return round(n / (n + floor), 3)


def _media(valores) -> float:
    return sum(valores) / len(valores) if valores else 0.0


def _finding_grupo(dimensao, valor, tipo, valores, baseline, floor) -> dict:
    n = len(valores)
    media = _media(valores)
    return {
        "dimensao": dimensao,
        "tipo": tipo,
        "valor": valor,
        "media": round(media, 3),
        "baseline": round(baseline, 3),
        "efeito": round(media - baseline, 3),
        "n": n,
        "confianca": _confianca(n, floor),
        "elegivel": n >= floor,
    }


def agregar(vetores: list[dict], cfg: dict) -> list[dict]:
    """Rollup por dimensão → lista de findings. `metrica` é a 1ª headline."""
    headline = cfg.get("metricas", {}).get("headline") or ["avg_view_pct"]
    metrica = headline[0]
    floor = int(cfg.get("sample_floor", 3))
    dimensoes = cfg.get("dimensoes") or []

    amostras = [
        (v["inputs"], v["metricas"][metrica], v)
        for v in vetores
        if metrica in (v.get("metricas") or {})
    ]
    if not amostras:
        return []

    baseline = _media([m for _, m, _ in amostras])
    findings = []

    for dim in dimensoes:
        if dim in DIMENSOES_CATEGORICAS:
            findings += _por_valor(dim, "categorico", amostras, baseline, floor, transform=None)
        elif dim in DIMENSOES_NUMERICAS:
            findings += _por_valor(dim, "numerico", amostras, baseline, floor, transform=_bucket)
        elif dim in DIMENSOES_TEXTUAIS:
            f = _textual(dim, metrica, amostras, baseline, floor)
            if f:
                findings.append(f)

    for f in findings:
        f["metrica"] = metrica
    # mais forte primeiro: elegíveis, |efeito| desc, confiança desc
    findings.sort(key=lambda f: (not f["elegivel"], -abs(f["efeito"]), -f["confianca"]))
    return findings


def _por_valor(dim, tipo, amostras, baseline, floor, transform) -> list[dict]:
    grupos: dict[str, list[float]] = {}
    for inputs, metrica_val, _ in amostras:
        bruto = inputs.get(dim)
        valor = transform(dim, bruto) if transform else bruto
        if valor is None or valor == "":
            continue
        grupos.setdefault(str(valor), []).append(metrica_val)
    return [
        _finding_grupo(dim, valor, tipo, valores, baseline, floor)
        for valor, valores in grupos.items()
    ]


def _textual(dim, metrica, amostras, baseline, floor) -> dict | None:
    com_texto = [
        (inputs[dim], mval)
        for inputs, mval, _ in amostras
        if inputs.get(dim)
    ]
    if not com_texto:
        return None
    ordenados = sorted(com_texto, key=lambda x: x[1], reverse=True)
    top = ordenados[:_TOP_EXEMPLOS]
    media_top = _media([m for _, m in top])
    n = len(com_texto)
    return {
        "dimensao": dim,
        "tipo": "textual",
        "valor": None,
        "media": round(media_top, 3),
        "baseline": round(baseline, 3),
        "efeito": round(media_top - baseline, 3),
        "n": n,
        "confianca": _confianca(n, floor),
        "elegivel": n >= floor,
        "exemplos": [t for t, _ in top],
        "piores": [t for t, _ in ordenados[-_TOP_EXEMPLOS:]] if n > _TOP_EXEMPLOS else [],
    }


def assinatura(vetores: list[dict]) -> str:
    """Hash estável dos inputs do cálculo (para pular recomputo idêntico)."""
    base = sorted(
        (v.get("video_id"), v.get("marco"), tuple(sorted((v.get("metricas") or {}).items())))
        for v in vetores
    )
    bruto = json.dumps(base, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]
