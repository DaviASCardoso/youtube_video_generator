from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

from config.tipos import TipoVideo, listar_tipos_ativos, carregar_tipo
from config.sistema import sistema
from scripts.execucoes import executar_com_captura, historico, ExecucaoEmAndamentoError
from scripts.tendencias import coletar_temas_do_dia

scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=sistema.get("execucao.max_simultaneo"))}
)

# Id reservado do job global de tendências (não é um tipo de vídeo). Os demais
# jobs usam o id do tipo; este prefixo com "__" não colide com um id de tipo
# (que é um slug de [a-z0-9_] sem "__" no começo).
_JOB_TENDENCIAS = "__tendencias__"


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


def _job_reservado(tipo_id: str, tema: str, execucao: dict) -> None:
    tipo = carregar_tipo(tipo_id)
    executar_com_captura(tema, tipo, execucao=execucao)


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


def disparar_agora(tipo: TipoVideo, tema: str | None = None) -> dict:
    """Reserva e dispara uma execução avulsa no MESMO scheduler/executor dos jobs de
    cron, para que "executar agora" respeite o mesmo teto de concorrência
    (execucao.max_simultaneo).

    O tema (se vindo da fila) e o registro de histórico são resolvidos aqui, de forma
    síncrona, para que o chamador já saiba o id da execução antes do trabalho pesado
    (gerar o vídeo) começar rodando em segundo plano.

    Args:
        tipo: Tipo de vídeo a executar.
        tema: Tema específico, ou None para consumir o próximo da fila.

    Returns:
        O registro de execução recém-criado (contém seu "id").

    Raises:
        ValueError: Se nenhum tema foi informado e a fila do tipo está vazia.
        ExecucaoEmAndamentoError: Se já existir uma execução em andamento para o tipo.
    """
    tema_final = tema or tipo.temas.proximo()
    if tema_final is None:
        raise ValueError(
            f"Fila de temas vazia para o tipo '{tipo.nome}' e nenhum tema foi informado."
        )

    execucao = historico.iniciar(tipo.id, tipo.nome, tema_final)

    scheduler.add_job(
        _job_reservado,
        trigger="date",
        run_date=datetime.now(),
        args=[tipo.id, tema_final, execucao],
        id=f"manual-{execucao['id']}",
    )
    return execucao


def _job_tendencias() -> None:
    coletar_temas_do_dia()


def registrar_job_tendencias() -> None:
    """Agenda (ou reagenda/remove) o job diário global de tendências, conforme as
    configurações do sistema (tendencias.ativo/horario/fuso_horario).

    Job único (não por tipo): busca as tendências do dia uma vez e alimenta a fila
    de cada tipo ativo. Chamado no start e sempre que as configurações mudam.
    """
    if not sistema.get("tendencias.ativo"):
        try:
            scheduler.remove_job(_JOB_TENDENCIAS)
        except JobLookupError:
            pass
        return

    horario = sistema.get("tendencias.horario")
    fuso = ZoneInfo(sistema.get("tendencias.fuso_horario"))
    hora, minuto = horario.split(":")

    scheduler.add_job(
        _job_tendencias,
        trigger=CronTrigger(hour=hora, minute=minuto, timezone=fuso),
        id=_JOB_TENDENCIAS,
        replace_existing=True,
    )


def atualizar_max_simultaneo(max_simultaneo: int) -> None:
    """Aplica uma mudança de execucao.max_simultaneo ao pool de execução em tempo real,
    sem precisar reiniciar o processo."""
    scheduler.remove_executor("default")
    scheduler.add_executor(ThreadPoolExecutor(max_workers=max_simultaneo), "default")


def iniciar() -> None:
    for tipo in listar_tipos_ativos():
        registrar_job(tipo)
    registrar_job_tendencias()
    scheduler.start()


def parar() -> None:
    scheduler.shutdown(wait=False)
