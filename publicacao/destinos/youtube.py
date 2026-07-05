"""Destino YouTube — o `publicacao/youtube.py` (OAuth por tipo, videos.insert)
embrulhado no contrato de destino, com metadados otimizados, publishAt e thumbnail.

Reusa a credencial por tipo já existente (`tipos/<id>/youtube_token.json`); nada novo
é configurado aqui. A thumbnail é best-effort: se falhar, o upload não é derrubado.
"""

from publicacao import youtube
from publicacao.destinos.base import registrar


@registrar("youtube")
class DestinoYoutube:
    def publicar(self, video_path, metadados: dict, thumb_path, opcoes: dict, tipo) -> dict:
        corpo = youtube.montar_corpo(metadados, opcoes)
        video_id = youtube.subir_video(tipo, video_path, corpo)

        if thumb_path:
            try:
                youtube.definir_thumbnail(tipo, video_id, thumb_path)
            except Exception as e:  # noqa: BLE001 (thumbnail não derruba a publicação)
                print(f"    [youtube] thumbnail falhou (o vídeo foi publicado): {e}")

        return {
            "id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "quota": youtube.QUOTA_UPLOAD,
            "privacidade": corpo["status"]["privacyStatus"],
            "agendado_para": corpo["status"].get("publishAt"),
        }

    def checar_credencial(self, tipo) -> dict:
        return youtube.checar_credencial(tipo)
