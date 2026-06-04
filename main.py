from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from config.settings import get
from scripts.pipeline import gerar_video

TEMAS = [
    "dicas de produtividade para estudantes",
    "como usar inteligência artificial no dia a dia",
    "hábitos de pessoas bem-sucedidas",
]

_tema_index = 0


def _proximo_tema() -> str:
    global _tema_index
    tema = TEMAS[_tema_index % len(TEMAS)]
    _tema_index += 1
    return tema


def _executar() -> None:
    tema = _proximo_tema()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path("output") / timestamp

    print(f"\n[{datetime.now()}] Iniciando geração do vídeo")
    print(f"Tema: {tema}")
    print(f"Saída: {output_path}\n")

    try:
        caminho = gerar_video(tema=tema, output_path=output_path)
        print(f"\n[{datetime.now()}] Vídeo concluído: {caminho}")
    except Exception as e:
        print(f"\n[{datetime.now()}] Erro na geração do vídeo: {e}")
        raise


def _configurar_trigger() -> CronTrigger:
    frequencia = get("agendamento.frequencia")
    horario = get("agendamento.horario")
    fuso = ZoneInfo(get("agendamento.fuso_horario"))
    hora, minuto = horario.split(":")

    triggers = {
        "daily":   CronTrigger(hour=hora, minute=minuto, timezone=fuso),
        "weekly":  CronTrigger(day_of_week="mon", hour=hora, minute=minuto, timezone=fuso),
        "monthly": CronTrigger(day=1, hour=hora, minute=minuto, timezone=fuso),
    }

    if frequencia not in triggers:
        raise ValueError(
            f"Frequência inválida: '{frequencia}'. "
            f"Opções válidas: {list(triggers.keys())}"
        )

    return triggers[frequencia]


def main() -> None:
    frequencia = get("agendamento.frequencia")
    horario = get("agendamento.horario")
    fuso = get("agendamento.fuso_horario")

    print("=== YouTube Video Generator ===")
    print(f"Frequência : {frequencia}")
    print(f"Horário    : {horario} ({fuso})")
    print("Aguardando próxima execução...\n")

    scheduler = BlockingScheduler()
    scheduler.add_job(_executar, trigger=_configurar_trigger())
    scheduler.start()


if __name__ == "__main__":
    main()