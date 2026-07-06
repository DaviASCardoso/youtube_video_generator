"""Ingestão de métricas na agenda de maturação.

Para um tipo, encontra os vídeos publicados (no histórico de execuções), decide quais
têm um marco de maturação devido (`maturacao`), puxa as métricas + curva de retenção
do destino de analytics e as guarda em `metricas.json`. Eficiente e degradável:
- só consulta um vídeo quando há marco devido (nunca re-puxa dado maturado/inalterado);
- uma consulta por vídeo por passada (o marco maior devido), marcando todos os marcos
  devidos como coletados com esse snapshot;
- destino desligado ⇒ passada inteira pulada (pilar inerte por default);
- falha de credencial/consulta ⇒ mantém o último dado bom (não sobrescreve, não quebra).
"""

from feedback.armazenamento import metricas_de
from feedback.configuracao import mesclar_feedback
from feedback.destinos import base as destinos
from feedback import maturacao


# Status de published-record que contam como "no ar" (têm métricas a coletar).
_STATUS_PUBLICADO = {"publicado", "agendado"}


def _videos_publicados(tipo, destinos_ativos: set) -> list[dict]:
    """Extrai (video_id, publicado_em, destino, execucao_id, tema) do histórico.

    Um vídeo entra quando um destino ativo tem um published-record com `id`. O
    `publicado_em` vem do agendamento do destino, senão do fim da execução.
    """
    from operacoes.execucoes import historico

    vistos = set()
    out = []
    for reg in historico.listar(tipo.id):
        publicado_em = reg.get("finalizado_em")
        for item in reg.get("publicacao", []):
            destino = item.get("destino")
            video_id = item.get("id")
            if not video_id or destino not in destinos_ativos:
                continue
            if item.get("status") not in _STATUS_PUBLICADO:
                continue
            quando = item.get("agendado_para") or publicado_em
            if not quando:
                continue
            chave = (destino, video_id)
            if chave in vistos:
                continue
            vistos.add(chave)
            out.append(
                {
                    "video_id": video_id,
                    "publicado_em": quando,
                    "destino": destino,
                    "execucao_id": reg.get("id"),
                    "tema": reg.get("tema"),
                }
            )
    return out


def ingerir(tipo, agora=None) -> dict:
    """Faz uma passada de ingestão para o tipo. Devolve um resumo observável."""
    cfg = mesclar_feedback(tipo.config.get_all().get("feedback"))
    ativos = {n for n, d in cfg["destinos"].items() if d.get("ativo")}
    if not ativos:
        return {"pulado": "destinos_desligados", "polados": [], "ignorados": []}

    store = metricas_de(tipo)
    chaves = cfg["metricas"]["ingeridas"]
    resumo = {"polados": [], "ignorados": [], "falhas": []}

    for rec in _videos_publicados(tipo, ativos):
        video_id = rec["video_id"]
        registro = store.video(video_id) or {}
        polls = registro.get("polls", {})
        devidos = maturacao.marcos_devidos(rec["publicado_em"], cfg["repoll_horas"], polls.keys(), agora)
        if not devidos:
            resumo["ignorados"].append(video_id)
            continue

        try:
            destino = destinos.obter(rec["destino"])
            dados = destino.metricas_do_video(tipo, video_id, rec["publicado_em"], chaves=chaves)
        except Exception:  # noqa: BLE001 — degrada por vídeo, não derruba a passada
            dados = None
        if dados is None:
            resumo["falhas"].append(video_id)
            continue

        marco = devidos[-1]
        snapshot = {**dados, "marco": marco}
        for h in devidos:
            polls[str(h)] = snapshot
        registro.update(
            {
                "tipo_id": tipo.id,
                "execucao_id": rec["execucao_id"],
                "tema": rec["tema"],
                "destino": rec["destino"],
                "publicado_em": str(rec["publicado_em"]),
                "polls": polls,
                "ultimo_marco": marco,
            }
        )
        store.gravar_video(video_id, registro)
        resumo["polados"].append(video_id)

    return resumo
