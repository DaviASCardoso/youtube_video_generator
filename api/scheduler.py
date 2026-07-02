from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

from config.tipos import TipoVideo, listar_tipos_ativos, carregar_tipo
from config.sistema import sistema
from scripts.execucoes import executar_com_captura, historico, ExecucaoEmAndamentoError

scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=sistema.get("execucao.max_simultaneo"))}
)


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


def _job_agendado(tipo_id: str) -> None:
    tipo = carregar_tipo(tipo_id)
    tema = tipo.temas.proximo()
    if tema is None:
        print(f"[{tipo.nome}] Fila de temas vazia, nada a gerar.")
        return
    try:
        executar_com_captura(tema, tipo)
    except ExecucaoEmAndamentoError:
        print(f"[{tipo.nome}] Já existe uma execução em andamento, pulando esta execução agendada.")


def _job_manual(tipo_id: str, tema: str | None) -> None:
    tipo = carregar_tipo(tipo_id)
    tema_final = tema or tipo.temas.proximo()
    if tema_final is None:
        print(f"[{tipo.nome}] Fila de temas vazia e nenhum tema informado, nada a gerar.")
        return
    executar_com_captura(tema_final, tipo)


def registrar_job(tipo: TipoVideo) -> None:
    """Agenda (ou reagenda) o job de cron de um tipo, a partir do seu agendamento atual."""
    scheduler.add_job(
        _job_agendado,
        trigger=_configurar_trigger(tipo),
        args=[tipo.id],
        id=tipo.id,
        replace_existing=True,
    )


def remover_job(tipo_id: str) -> None:
    """Remove o job de cron de um tipo, se existir (não é erro se não existir)."""
    try:
        scheduler.remove_job(tipo_id)
    except JobLookupError:
        pass


def reagendar_job(id_antigo: str, tipo: TipoVideo) -> None:
    """Move o job de cron de id_antigo para o (novo) id do tipo. Usado após renomear um tipo."""
    remover_job(id_antigo)
    if tipo.ativo:
        registrar_job(tipo)


def disparar_agora(tipo: TipoVideo, tema: str | None = None) -> str:
    """Submete uma execução avulsa no MESMO scheduler/executor dos jobs de cron, para que
    "executar agora" respeite o mesmo teto de concorrência (execucao.max_simultaneo).

    Args:
        tipo: Tipo de vídeo a executar.
        tema: Tema específico, ou None para consumir o próximo da fila.

    Returns:
        Id do job avulso criado no scheduler.

    Raises:
        ExecucaoEmAndamentoError: Se já existir uma execução em andamento para o tipo
            (checagem rápida; a garantia real acontece de forma atômica dentro da execução).
    """
    if historico.em_execucao(tipo.id):
        raise ExecucaoEmAndamentoError(
            f"Já existe uma execução em andamento para o tipo '{tipo.id}'."
        )

    job_id = f"manual-{tipo.id}-{uuid4().hex[:8]}"
    scheduler.add_job(
        _job_manual, trigger="date", run_date=datetime.now(), args=[tipo.id, tema], id=job_id
    )
    return job_id


def atualizar_max_simultaneo(max_simultaneo: int) -> None:
    """Aplica uma mudança de execucao.max_simultaneo ao pool de execução em tempo real,
    sem precisar reiniciar o processo."""
    scheduler.remove_executor("default")
    scheduler.add_executor(ThreadPoolExecutor(max_workers=max_simultaneo), "default")


def iniciar() -> None:
    for tipo in listar_tipos_ativos():
        registrar_job(tipo)
    scheduler.start()


def parar() -> None:
    scheduler.shutdown(wait=False)
