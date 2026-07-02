from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from config.tipos import TipoVideo, listar_tipos_ativos
from config.sistema import sistema
from scripts.pipeline import gerar_video


def _executar(tipo: TipoVideo) -> None:
    tema = tipo.temas.proximo()
    if tema is None:
        print(f"\n[{datetime.now()}] [{tipo.nome}] Fila de temas vazia, nada a gerar.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(sistema.get("saida.pasta_base")) / tipo.id / timestamp

    print(f"\n[{datetime.now()}] [{tipo.nome}] Iniciando geração do vídeo")
    print(f"Tema: {tema}")
    print(f"Saída: {output_path}\n")

    try:
        caminho = gerar_video(tema=tema, tipo=tipo, output_path=output_path)
        print(f"\n[{datetime.now()}] [{tipo.nome}] Vídeo concluído: {caminho}")
    except Exception as e:
        print(f"\n[{datetime.now()}] [{tipo.nome}] Erro na geração do vídeo: {e}")
        raise


def _configurar_trigger(tipo: TipoVideo) -> CronTrigger:
    frequencia = tipo.config.get("agendamento.frequencia")
    horario = tipo.config.get("agendamento.horario")
    fuso = ZoneInfo(tipo.config.get("agendamento.fuso_horario"))
    hora, minuto = horario.split(":")

    triggers = {
        "daily":   CronTrigger(hour=hora, minute=minuto, timezone=fuso),
        "weekly":  CronTrigger(day_of_week="mon", hour=hora, minute=minuto, timezone=fuso),
        "monthly": CronTrigger(day=1, hour=hora, minute=minuto, timezone=fuso),
    }

    if frequencia not in triggers:
        raise ValueError(
            f"Frequência inválida para o tipo '{tipo.id}': '{frequencia}'. "
            f"Opções válidas: {list(triggers.keys())}"
        )

    return triggers[frequencia]


def main() -> None:
    tipos = listar_tipos_ativos()

    if not tipos:
        raise RuntimeError("Nenhum tipo de vídeo ativo encontrado em tipos/.")

    max_simultaneo = sistema.get("execucao.max_simultaneo")

    print("=== YouTube Video Generator ===")
    for tipo in tipos:
        frequencia = tipo.config.get("agendamento.frequencia")
        horario = tipo.config.get("agendamento.horario")
        fuso = tipo.config.get("agendamento.fuso_horario")
        print(f"Tipo       : {tipo.nome} ({tipo.id})")
        print(f"Frequência : {frequencia}")
        print(f"Horário    : {horario} ({fuso})")
    print(f"Execução   : até {max_simultaneo} vídeo(s) simultâneo(s)")
    print("Aguardando próximas execuções...\n")

    # execucao.max_simultaneo em config/sistema.json controla quantos vídeos
    # podem ser gerados ao mesmo tempo (1 = sequencial, mesmo entre tipos diferentes).
    scheduler = BlockingScheduler(executors={"default": ThreadPoolExecutor(max_workers=max_simultaneo)})

    for tipo in tipos:
        scheduler.add_job(_executar, trigger=_configurar_trigger(tipo), args=[tipo], id=tipo.id)

    scheduler.start()


if __name__ == "__main__":
    main()
