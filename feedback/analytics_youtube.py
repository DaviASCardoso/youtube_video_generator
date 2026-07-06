"""Cliente de baixo nível da YouTube Analytics API v2 (+ Data API v3).

Puxa as métricas do dono do canal por vídeo — retenção (averageViewPercentage),
watch time, views, inscritos ganhos — e a **curva de retenção** (audienceWatchRatio
por elapsedVideoTimeRatio). Reusa a credencial OAuth **por tipo** de
`publicacao.youtube` (mesmo client, sem segredo novo); a única exigência é a YouTube
Analytics API habilitada e o escopo `yt-analytics.readonly` (já em
`publicacao.youtube.ESCOPOS`), com um reconsentimento.

Degrada em vez de quebrar: qualquer falha de credencial/rede/campo indisponível faz
`coletar` devolver `None` (a ingestão mantém o último dado bom). A CTR de impressão
não é exposta de forma estável pela Analytics API pública; é pedida como best-effort e,
se a consulta inteira falhar por causa dela, cai para um conjunto núcleo de métricas.

Testável offline: `_servico_analytics`, `_servico_data` e `_canal_id` são funções de
módulo mockadas nos testes (nenhuma chamada real na suíte).
"""

from datetime import date, datetime, timezone

from googleapiclient.discovery import build

from publicacao.youtube import autenticar
from publicacao.youtube import _servico as _servico_data_v3  # Data API v3 (reuso)

# Mapeia nossas chaves internas para os nomes de métrica da Analytics API.
_MAPA_METRICAS = {
    "avg_view_pct": "averageViewPercentage",
    "views": "views",
    "watch_time": "estimatedMinutesWatched",
    "subs": "subscribersGained",
    "ctr": "cardClickRate",  # best-effort; pode não estar disponível
}

# Conjunto núcleo (bem suportado) para o retry quando a consulta cheia falha.
_METRICAS_NUCLEO = ("avg_view_pct", "views", "watch_time", "subs")


def _servico_analytics(tipo):
    """Serviço da YouTube Analytics API v2 para o canal do tipo."""
    creds = autenticar(tipo)
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def _servico_data(tipo):
    """Serviço da Data API v3 (contadores públicos), reusando publicacao.youtube."""
    return _servico_data_v3(tipo)


def _canal_id(tipo) -> str:
    """Id do canal autenticado (necessário como ids=channel==<id>)."""
    resp = _servico_data(tipo).channels().list(part="id", mine=True).execute()
    itens = resp.get("items", [])
    if not itens:
        raise RuntimeError("Nenhum canal associado à conta autenticada.")
    return itens[0]["id"]


def _hoje() -> date:
    return datetime.now(timezone.utc).date()


def _dia(valor) -> date:
    """Normaliza um ISO/date para date (para o startDate da consulta)."""
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).date()


def _linha_metricas(servico, canal, video_id, inicio, fim, chaves):
    api_metricas = [_MAPA_METRICAS[k] for k in chaves if k in _MAPA_METRICAS]
    resp = (
        servico.reports()
        .query(
            ids=f"channel=={canal}",
            startDate=inicio.isoformat(),
            endDate=fim.isoformat(),
            metrics=",".join(api_metricas),
            filters=f"video=={video_id}",
        )
        .execute()
    )
    linhas = resp.get("rows") or []
    if not linhas:
        return {}
    valores = linhas[0]
    return {k: valores[i] for i, k in enumerate(chaves) if k in _MAPA_METRICAS and i < len(valores)}


def _consultar_metricas(servico, canal, video_id, inicio, fim, chaves) -> dict:
    """Consulta as métricas pedidas; se a consulta cheia falhar, cai no núcleo."""
    try:
        return _linha_metricas(servico, canal, video_id, inicio, fim, chaves)
    except Exception:  # noqa: BLE001
        nucleo = [k for k in chaves if k in _METRICAS_NUCLEO]
        if not nucleo or set(nucleo) == set(chaves):
            return {}
        try:
            return _linha_metricas(servico, canal, video_id, inicio, fim, nucleo)
        except Exception:  # noqa: BLE001
            return {}


def _consultar_curva(servico, canal, video_id, inicio, fim) -> list:
    """Curva de retenção: audienceWatchRatio por elapsedVideoTimeRatio."""
    try:
        resp = (
            servico.reports()
            .query(
                ids=f"channel=={canal}",
                startDate=inicio.isoformat(),
                endDate=fim.isoformat(),
                metrics="audienceWatchRatio",
                dimensions="elapsedVideoTimeRatio",
                filters=f"video=={video_id}",
                sort="elapsedVideoTimeRatio",
            )
            .execute()
        )
        linhas = resp.get("rows") or []
        return [[float(r[0]), float(r[1])] for r in linhas if len(r) >= 2]
    except Exception:  # noqa: BLE001
        return []


def coletar(tipo, video_id: str, publicado_em, chaves=None) -> dict | None:
    """Coleta métricas + curva de retenção de um vídeo. `None` se nada pôde ser lido.

    Args:
        tipo: O tipo de vídeo (dono da credencial).
        video_id: Id do vídeo na plataforma.
        publicado_em: Quando foi publicado (ISO/date) — startDate da janela.
        chaves: Métricas internas a pedir (default: todas as mapeadas).

    Returns:
        Dict com as métricas lidas + `curva` (lista [elapsed, watch]) + `coletado_em`,
        ou `None` se a credencial/consulta falhou por inteiro (mantém o último dado bom).
    """
    chaves = list(chaves) if chaves else list(_MAPA_METRICAS)
    try:
        servico = _servico_analytics(tipo)
        canal = _canal_id(tipo)
    except Exception:  # noqa: BLE001 — sem credencial/canal: mantém o último dado bom
        return None

    inicio = _dia(publicado_em)
    fim = _hoje()
    if fim < inicio:
        fim = inicio

    metricas = _consultar_metricas(servico, canal, video_id, inicio, fim, chaves)
    curva = _consultar_curva(servico, canal, video_id, inicio, fim)

    if not metricas and not curva:
        return None

    return {**metricas, "curva": curva, "coletado_em": datetime.now(timezone.utc).isoformat()}


def checar(tipo) -> dict:
    """Verificação não-destrutiva: a credencial lê o canal? {status, detalhe}."""
    try:
        canal = _canal_id(tipo)
        return {"status": "valido", "detalhe": canal}
    except Exception as e:  # noqa: BLE001
        return {"status": "erro", "detalhe": str(e)}
