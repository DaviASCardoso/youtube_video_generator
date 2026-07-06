"""Destino de analytics: YouTube (Analytics API v2 + Data API v3).

Fino: encaminha para `feedback.analytics_youtube`, que faz o trabalho de baixo nível
reusando a credencial OAuth por tipo. Existe para que o Feedback fale com "um destino"
e não com o YouTube diretamente — TikTok/Reels entram implementando o mesmo contrato.
"""

from feedback import analytics_youtube
from feedback.destinos.base import registrar


@registrar("youtube")
class DestinoAnalyticsYoutube:
    def metricas_do_video(self, tipo, video_id: str, publicado_em, chaves=None) -> dict | None:
        return analytics_youtube.coletar(tipo, video_id, publicado_em, chaves=chaves)

    def checar(self, tipo) -> dict:
        return analytics_youtube.checar(tipo)
