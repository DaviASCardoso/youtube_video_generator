"""Fonte de sinal: YouTube Data API v3.

Duas leituras: o que as pessoas buscam (search.list por `consultas`, ordenado por
viewCount na região do tipo) e o que canais do mesmo nicho publicaram
recentemente (`canais_nicho`, ordenado por data). Os candidatos são os títulos
dos vídeos, já normalizados por rank.

Reusa o OAuth por tipo da Publicação (`publicacao.youtube._servico`) — mesma
credencial/canal, escopo youtube.readonly já presente. Sem token válido, a
chamada levanta e o registro (base.coletar) apenas pula a fonte.

Cuidado de cota: search.list custa ~100 unidades por chamada, compartilhada com
o upload — por isso esta fonte vem **desligada por padrão**.
"""

from descoberta.fontes import base
from publicacao import youtube as _yt


def _titulos(resposta: dict) -> list[str]:
    titulos = []
    for item in resposta.get("items", []):
        titulo = item.get("snippet", {}).get("title", "").strip()
        if titulo:
            titulos.append(titulo)
    return titulos


@base.registrar("youtube")
def buscar(tipo, cfg: dict) -> list:
    limite = min(int(cfg.get("limite", 15)), 50)
    consultas = cfg.get("consultas") or []
    canais = cfg.get("canais_nicho") or []
    regiao = cfg.get("regiao", "BR")

    servico = _yt._servico(tipo)  # levanta sem token → base.coletar pula a fonte
    titulos: list[str] = []

    for consulta in consultas:
        resposta = (
            servico.search()
            .list(
                q=consulta,
                part="snippet",
                type="video",
                order="viewCount",
                regionCode=regiao,
                maxResults=limite,
            )
            .execute()
        )
        titulos.extend(_titulos(resposta))

    for canal in canais:
        resposta = (
            servico.search()
            .list(
                channelId=canal,
                part="snippet",
                type="video",
                order="date",
                maxResults=limite,
            )
            .execute()
        )
        titulos.extend(_titulos(resposta))

    return base.candidatos_por_rank(titulos, "youtube")
