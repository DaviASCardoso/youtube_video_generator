"""Atribuição: liga a performance de cada vídeo aos inputs que o produziram.

Junta o registro de métricas (o mais maduro coletado) com o vetor de inputs do vídeo,
lido **do que já foi gravado** — sem forçar nenhum pilar upstream a registrar campo
novo:

  fonte / categoria / fit_score  ← histórico da Descoberta (tema decidido), casado por tema
  modo_visual / hook / duracao   ← sidecar.json da Geração
  titulo / thumbnail             ← publicacao.json (metadados/thumb escolhidos)
  publish_time                   ← hora de publicação (do registro de métricas)
  voz                            ← config do tipo (aproximação: não é gravada por vídeo)

Atribui no que existe: quando um join não casa (tema sem decisão, run sem sidecar), o
input fica `None` e a agregação simplesmente o ignora — degrada, não quebra.
"""

from feedback.armazenamento import metricas_de
from feedback import maturacao


def _norm(texto: str) -> str:
    from descoberta.tendencias import _normalizar

    return _normalizar(texto or "")


def _hora(publicado_em) -> int | None:
    if not publicado_em:
        return None
    try:
        return maturacao._para_dt(publicado_em).hour
    except (ValueError, TypeError):
        return None


def _modo_visual(sidecar: dict, config) -> str | None:
    # A Geração grava `modo_visual` explicitamente; casos antigos (sidecar sem a
    # chave) caem na dedução pelos provedores e, por fim, no config do tipo.
    explicito = sidecar.get("modo_visual")
    if explicito:
        return explicito
    provs = " ".join(str(v) for v in (sidecar.get("provedores") or {}).values()).lower()
    if "pexels" in provs:
        return "personagem"
    if "flux" in provs:
        return "ia"
    try:
        return config.get("imagens.modo")
    except Exception:  # noqa: BLE001
        return None


def _hook(sidecar: dict) -> str | None:
    # A Geração grava `hook` explicitamente; sidecars antigos caem na 1ª linha do roteiro.
    explicito = sidecar.get("hook")
    if explicito:
        return str(explicito).strip() or None
    roteiro = sidecar.get("roteiro")
    if not roteiro:
        return None
    primeira = str(roteiro).splitlines()[0].strip()
    return primeira or None


def maduras(registro: dict):
    """Métricas do marco mais maduro coletado. Devolve (metricas, curva, marco)."""
    polls = registro.get("polls") or {}
    if not polls:
        return {}, [], None
    marco = max(int(k) for k in polls)
    snap = polls[str(marco)]
    metricas = {k: v for k, v in snap.items() if k not in ("curva", "coletado_em", "marco")}
    return metricas, snap.get("curva") or [], marco


def _contexto(tipo):
    """(decididos_por_tema, execucoes_por_id, pasta_de) — as fontes do join."""
    from operacoes.execucoes import historico, pasta_da_execucao
    from descoberta.estado import historico_de

    decididos = {}
    for r in historico_de(tipo).listar():
        d = r.get("decidido")
        if d and d.get("tema"):
            decididos[_norm(d["tema"])] = d

    execucoes = {r["id"]: r for r in historico.listar(tipo.id)}
    return decididos, execucoes, pasta_da_execucao


def inputs_de(tipo, registro: dict, ctx) -> dict:
    """Vetor de inputs de um vídeo, do que foi gravado (campo ausente ⇒ None)."""
    from geracao import sidecar as sidecar_mod
    from publicacao import registro as registro_pub

    decididos, execucoes, pasta_de = ctx
    decidido = decididos.get(_norm(registro.get("tema") or ""), {})

    rec_exec = execucoes.get(registro.get("execucao_id"))
    pasta = pasta_de(rec_exec) if rec_exec else None
    sidecar = (sidecar_mod.ler(pasta) or {}) if pasta else {}
    pub = registro_pub.ler(pasta) if pasta else {}

    return {
        "fonte": decidido.get("fonte"),
        "categoria": decidido.get("categoria"),
        "fit_score": decidido.get("fit_score"),
        "voz": _voz(tipo),
        "modo_visual": _modo_visual(sidecar, tipo.config),
        "hook": _hook(sidecar),
        "titulo": (pub.get("metadados") or {}).get("titulo"),
        "publish_time": _hora(registro.get("publicado_em")),
        "duracao": sidecar.get("duracao_seg"),
        "thumbnail": bool(pub.get("thumbnail")),
    }


def _voz(tipo):
    try:
        return tipo.config.get("tts.voz")
    except Exception:  # noqa: BLE001
        return None


def atribuir(tipo) -> list[dict]:
    """Um vetor {video_id, tema, metricas, curva, inputs} por vídeo com dado maduro."""
    ctx = _contexto(tipo)
    store = metricas_de(tipo)
    out = []
    for registro in store.videos():
        metricas, curva, marco = maduras(registro)
        if not metricas and not curva:
            continue
        out.append(
            {
                "video_id": registro["id"],
                "tema": registro.get("tema"),
                "execucao_id": registro.get("execucao_id"),
                "marco": marco,
                "metricas": metricas,
                "curva": curva,
                "inputs": inputs_de(tipo, registro, ctx),
            }
        )
    return out
