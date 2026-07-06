"""Agenda de maturação do re-poll de analytics.

Analytics amadurecem devagar e têm cota, então cada vídeo é re-consultado só nos
marcos configurados (default ≈24h, 72h, 7d, 30d após publicar) e, depois do último,
para. Funções puras que decidem, dado o momento de publicação e os marcos já
coletados, qual marco (se algum) está devido agora — a ingestão usa isso para nunca
re-puxar dado inalterado.
"""

from datetime import datetime, timezone


def _para_dt(valor) -> datetime:
    """Normaliza ISO/datetime para datetime aware (UTC)."""
    if isinstance(valor, datetime):
        dt = valor
    else:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def horas_desde(publicado_em, agora=None) -> float:
    """Horas decorridas desde a publicação."""
    agora = agora or datetime.now(timezone.utc)
    delta = agora - _para_dt(publicado_em)
    return delta.total_seconds() / 3600.0


def marcos_devidos(publicado_em, repoll_horas, ja_coletados, agora=None) -> list[int]:
    """Marcos cuja janela já passou e que ainda não foram coletados (ordenados).

    Args:
        publicado_em: Quando o vídeo foi publicado (ISO/datetime).
        repoll_horas: Marcos da agenda (ex.: [24, 72, 168, 720]).
        ja_coletados: Conjunto/lista de marcos (int) já coletados.
        agora: Momento de referência (default: now UTC).
    """
    decorridas = horas_desde(publicado_em, agora)
    ja = {int(h) for h in ja_coletados}
    return sorted(int(h) for h in repoll_horas if decorridas >= h and int(h) not in ja)


def alvo(publicado_em, repoll_horas, ja_coletados, agora=None) -> int | None:
    """O marco a coletar agora — o **maior** devido (o dado mais maduro), ou None.

    Devolver o maior devido (e marcar todos os devidos como coletados) evita "correr
    atrás" marco a marco quando o job ficou parado por dias.
    """
    devidos = marcos_devidos(publicado_em, repoll_horas, ja_coletados, agora)
    return devidos[-1] if devidos else None


def maturado(publicado_em, repoll_horas, ja_coletados, agora=None) -> bool:
    """True quando não há mais nada a coletar: todos os marcos já foram coletados
    (independentemente do tempo — o último marco já passou e foi lido)."""
    ja = {int(h) for h in ja_coletados}
    return all(int(h) in ja for h in repoll_horas)
