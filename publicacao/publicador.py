"""Orquestrador da Publicação — do arquivo final ao vídeo no ar.

`publicar(tipo, pasta_run, execucao_id, ledger)` executa o fluxo da spec:

    sidecar → metadados (Groq) → thumbnail → [gate de revisão] → por destino ativo:
    idempotência → cota → credencial → upload (imediato/agendado) → published-record

Eficiência e resiliência: metadados/thumbnail são checkpointados (nunca refeitos);
um destino já publicado não sobe de novo (idempotência); a cota diária por credencial
adia em vez de esgotar; e **cada destino degrada sozinho** — um que falha (erro, cota,
credencial) é registrado e pulado, os outros seguem, e o run não quebra (o vídeo já
está no disco). Sem destino ativo, não publica — o comportamento default de hoje.
"""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from config.tipos import carregar_tipo
from publicacao import metadados as metadados_mod
from publicacao import thumbnail as thumbnail_mod
from publicacao.configuracao import mesclar_publicacao
from publicacao.destinos import base
from publicacao.quota import checar_cap, quota_diaria


def _destinos_ativos(cfg: dict) -> list[tuple[str, dict]]:
    return [(nome, d) for nome, d in cfg["destinos"].items() if d.get("ativo")]


def _publish_at(timing: dict) -> str | None:
    """Horário de go-live (ISO-8601 UTC) quando o timing é agendado; None se imediato.
    Usa a próxima ocorrência do horário configurado no fuso do tipo."""
    if timing.get("modo") != "agendado":
        return None
    tz = ZoneInfo(timing["fuso_horario"])
    agora = datetime.now(tz)
    hora, minuto = (int(x) for x in timing["horario"].split(":"))
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return alvo.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def _montar_opcoes(cfg: dict, dcfg: dict) -> dict:
    return {
        "privacidade": cfg["visibilidade"]["privacidade"],
        "audiencia": cfg["visibilidade"]["audiencia"],
        "disclosure_sintetico": cfg["visibilidade"]["disclosure_sintetico"],
        "categoria_id": dcfg.get("categoria_id", "22"),
        "idioma": dcfg.get("idioma", ""),
        "tags_base": dcfg.get("tags_base", []),
        "descricao_base": dcfg.get("descricao_base", ""),
        "publish_at": _publish_at(cfg["timing"]),
    }


def _subir_aos_destinos(tipo, pasta_run, execucao_id, metadados, thumb_path, cfg, ledger):
    """Sobe para cada destino ativo, degradando por destino. Import tardio do
    histórico para evitar ciclo (operacoes.execucoes importa este módulo)."""
    from operacoes.execucoes import historico

    video_path = Path(pasta_run) / "video_final.mp4"
    disclosure = cfg["visibilidade"]["disclosure_sintetico"]

    for nome, dcfg in _destinos_ativos(cfg):
        # Idempotência: um destino já publicado neste run não sobe de novo.
        ja = historico.publicacao_de(execucao_id, nome)
        if ja and ja.get("id"):
            print(f"    [{nome}] já publicado ({ja.get('url')}) — reconciliando, sem reenviar")
            continue

        try:
            destino = base.obter(nome)
        except KeyError:
            print(f"    [{nome}] destino não implementado — pulando")
            historico.registrar_publicacao_destino(execucao_id, nome, {"status": "nao_implementado"})
            continue

        cred = destino.checar_credencial(tipo)
        if cred["status"] in ("ausente", "expirado"):
            print(f"    [{nome}] credencial {cred['status']}: {cred['detalhe']} — pulando")
            historico.registrar_publicacao_destino(
                execucao_id, nome, {"status": f"credencial_{cred['status']}", "detalhe": cred["detalhe"]}
            )
            continue

        credencial = f"{nome}:{tipo.id}"
        if not checar_cap(quota_diaria.uploads_hoje(credencial), cfg["quota"]["cap_diario"]):
            print(f"    [{nome}] cota diária atingida — adiando para amanhã")
            historico.registrar_publicacao_destino(execucao_id, nome, {"status": "adiado_cota"})
            continue

        opcoes = _montar_opcoes(cfg, dcfg)
        try:
            res = destino.publicar(video_path, metadados, thumb_path, opcoes, tipo)
        except Exception as e:  # noqa: BLE001 (degrada por destino, não derruba o run)
            print(f"    [{nome}] upload falhou: {e}")
            historico.registrar_publicacao_destino(execucao_id, nome, {"status": "erro", "erro": str(e)})
            continue

        quota_diaria.registrar(credencial)
        if ledger is not None:
            ledger.registrar(f"upload_{nome}", nome, 0.0, quota=res.get("quota"))
        historico.registrar_publicacao_destino(
            execucao_id, nome,
            {
                "id": res["id"], "url": res["url"], "quota": res.get("quota"),
                "privacidade": res.get("privacidade"), "agendado_para": res.get("agendado_para"),
                "disclosure_sintetico": disclosure,
                "status": "agendado" if res.get("agendado_para") else "publicado",
            },
        )
        print(f"    [{nome}] publicado: {res['url']}")


def publicar(tipo, pasta_run, execucao_id, ledger=None) -> str:
    """Publica um run já gerado. Devolve o desfecho: "sem_destino", "aguardando_revisao"
    ou "publicado" (este último mesmo com destinos parcialmente degradados)."""
    from operacoes.execucoes import historico

    cfg = mesclar_publicacao(tipo.config.get_all().get("publicacao"))
    if not _destinos_ativos(cfg):
        return "sem_destino"  # nada ligado → não publica (default de hoje)

    metadados = metadados_mod.obter_metadados(pasta_run, tipo.config, tipo.assets_dir, ledger=ledger)
    thumb_path = thumbnail_mod.obter_thumbnail(pasta_run, tipo.config, tipo.assets_dir, ledger=ledger)

    if cfg["revisao"] == "revisar":
        print("Publicação em modo revisão — metadados/thumbnail prontos, aguardando aprovação.")
        historico.marcar_aguardando_publicacao(execucao_id)
        return "aguardando_revisao"

    _subir_aos_destinos(tipo, pasta_run, execucao_id, metadados, thumb_path, cfg, ledger)
    return "publicado"


def publicar_aprovado(execucao_id, ledger=None) -> str:
    """Caminho do botão "Aprovar & publicar" do gate de revisão: sobe reaproveitando os
    metadados/thumbnail já checkpointados e conclui a execução."""
    from operacoes.execucoes import historico, pasta_da_execucao

    registro_exec = historico.obter(execucao_id)
    tipo = carregar_tipo(registro_exec["tipo_id"])
    pasta = pasta_da_execucao(registro_exec)
    if pasta is None:
        raise ValueError("Execução sem pasta de run para publicar.")

    cfg = mesclar_publicacao(tipo.config.get_all().get("publicacao"))
    metadados = metadados_mod.obter_metadados(pasta, tipo.config, tipo.assets_dir, ledger=ledger)
    thumb_path = thumbnail_mod.obter_thumbnail(pasta, tipo.config, tipo.assets_dir, ledger=ledger)

    _subir_aos_destinos(tipo, pasta, execucao_id, metadados, thumb_path, cfg, ledger)
    historico.concluir(execucao_id, Path(pasta) / "video_final.mp4")
    return "publicado"
