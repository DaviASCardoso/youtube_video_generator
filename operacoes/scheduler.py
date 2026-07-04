from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

from config.tipos import TipoVideo, listar_tipos_ativos, carregar_tipo
from config.sistema import sistema
from descoberta import estado
from descoberta.configuracao import mesclar_descoberta
from descoberta.descoberta import decidir_tema
from operacoes.execucoes import executar_com_captura, historico, ExecucaoEmAndamentoError

scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=sistema.get("execucao.max_simultaneo"))}
)

# Sufixo do id do job de descoberta de um tipo (o job de geração usa o id do tipo).
_SUFIXO_DESCOBERTA = "__descoberta"

# Base de referência (uma segunda-feira, dia 1) para calcular o horário deslocado
# "X horas antes" da geração, resolvendo viradas de dia/semana corretamente.
_BASE_REF = datetime(2024, 1, 1)  # 2024-01-01 é uma segunda-feira
_DIAS_SEMANA = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _antecedencia(tipo: TipoVideo) -> int:
    cfg = mesclar_descoberta(tipo.config.get_all().get("descoberta"))
    return cfg["antecedencia_horas"]


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


def _trigger_descoberta(tipo: TipoVideo, horas: int) -> CronTrigger:
    """Cron da descoberta: `horas` antes do horário de geração do tipo.

    Diário e semanal são exatos (a virada de dia/semana é resolvida via datetime).
    Mensal é aproximado: o dia é limitado a 28 para garantir disparo em todo mês
    (o dia-do-mês exato dependeria do tamanho do mês).
    """
    frequencia = tipo.config.get("agendamento.frequencia")
    horario = tipo.config.get("agendamento.horario")
    fuso = ZoneInfo(tipo.config.get("agendamento.fuso_horario"))
    hora, minuto = (int(x) for x in horario.split(":"))

    alvo = _BASE_REF.replace(hour=hora, minute=minuto) - timedelta(hours=horas)

    if frequencia == "daily":
        return CronTrigger(hour=alvo.hour, minute=alvo.minute, timezone=fuso)
    if frequencia == "weekly":
        return CronTrigger(
            day_of_week=_DIAS_SEMANA[alvo.weekday()],
            hour=alvo.hour,
            minute=alvo.minute,
            timezone=fuso,
        )
    if frequencia == "monthly":
        return CronTrigger(
            day=min(alvo.day, 28), hour=alvo.hour, minute=alvo.minute, timezone=fuso
        )
    raise ValueError(f"Frequência inválida para o tipo '{tipo.id}': '{frequencia}'.")


def _gerar_do_slot(tipo: TipoVideo) -> None:
    """Lê o tema decidido no slot; se estiver pronto, gera (e limpa o slot)."""
    slot = estado.slot_de(tipo)
    decisao = slot.ler()
    if decisao is None:
        print(f"[{tipo.nome}] Sem tema decidido no slot, nada a gerar.")
        return
    if decisao.estado != "pronto":
        print(f"[{tipo.nome}] Tema decidido aguardando aprovação (revisão), pulando geração.")
        return
    slot.limpar()
    try:
        executar_com_captura(decisao.tema, tipo)
    except ExecucaoEmAndamentoError:
        print(f"[{tipo.nome}] Já existe uma execução em andamento, pulando esta execução agendada.")


def _job_agendado(tipo_id: str) -> None:
    tipo = carregar_tipo(tipo_id)
    # Sem antecedência, a descoberta roda aqui, imediatamente antes da geração.
    if _antecedencia(tipo) == 0:
        try:
            decidir_tema(tipo)
        except Exception as e:
            print(f"[{tipo.nome}] Falha na descoberta: {e}")
    _gerar_do_slot(tipo)


def _job_descoberta(tipo_id: str) -> None:
    tipo = carregar_tipo(tipo_id)
    try:
        decidir_tema(tipo)
    except Exception as e:
        print(f"[{tipo.nome}] Falha na descoberta: {e}")


def _job_reservado(tipo_id: str, tema: str, execucao: dict) -> None:
    tipo = carregar_tipo(tipo_id)
    executar_com_captura(tema, tipo, execucao=execucao)


def registrar_job(tipo: TipoVideo) -> None:
    """Agenda (ou reagenda) os jobs de um tipo: a geração no horário configurado e,
    se `antecedencia_horas` > 0, a descoberta esse tanto de horas antes."""
    scheduler.add_job(
        _job_agendado,
        trigger=_configurar_trigger(tipo),
        args=[tipo.id],
        id=tipo.id,
        replace_existing=True,
    )

    id_descoberta = f"{tipo.id}{_SUFIXO_DESCOBERTA}"
    horas = _antecedencia(tipo)
    if horas > 0:
        scheduler.add_job(
            _job_descoberta,
            trigger=_trigger_descoberta(tipo, horas),
            args=[tipo.id],
            id=id_descoberta,
            replace_existing=True,
        )
    else:
        _remover(id_descoberta)


def _remover(job_id: str) -> None:
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass


def remover_job(tipo_id: str) -> None:
    """Remove os jobs (geração + descoberta) de um tipo, se existirem."""
    _remover(tipo_id)
    _remover(f"{tipo_id}{_SUFIXO_DESCOBERTA}")


def reagendar_job(id_antigo: str, tipo: TipoVideo) -> None:
    """Move os jobs de id_antigo para o (novo) id do tipo. Usado após renomear um tipo."""
    remover_job(id_antigo)
    if tipo.ativo:
        registrar_job(tipo)


def disparar_agora(tipo: TipoVideo, tema: str | None = None) -> dict:
    """Reserva e dispara uma execução avulsa no MESMO scheduler/executor dos jobs de
    cron, para que "executar agora" respeite o mesmo teto de concorrência
    (execucao.max_simultaneo).

    O tema e o registro de histórico são resolvidos aqui, de forma síncrona, para
    que o chamador já saiba o id da execução antes do trabalho pesado começar.
    Sem um tema explícito: consome um tema já decidido e pronto no slot; se não
    houver, roda a descoberta na hora.

    Args:
        tipo: Tipo de vídeo a executar.
        tema: Tema específico (digitado no painel), ou None para deixar a
            Descoberta decidir.

    Returns:
        O registro de execução recém-criado (contém seu "id").

    Raises:
        ValueError: Se nenhum tema foi informado e a Descoberta não decidiu um
            tema pronto (nada encontrado, ou aguardando aprovação na revisão).
        ExecucaoEmAndamentoError: Se já existir uma execução em andamento para o tipo.
    """
    if tema:
        tema_final = tema
    else:
        slot = estado.slot_de(tipo)
        decisao = slot.ler()
        if decisao is not None and decisao.estado == "pronto":
            tema_final = decisao.tema
            slot.limpar()
        else:
            decidida = decidir_tema(tipo)
            if decidida is None:
                raise ValueError(
                    f"A Descoberta não encontrou nenhum tema para o tipo '{tipo.nome}'."
                )
            if decidida.estado != "pronto":
                raise ValueError(
                    f"O tema decidido para '{tipo.nome}' aguarda aprovação (modo revisão)."
                )
            tema_final = decidida.tema
            estado.slot_de(tipo).limpar()

    execucao = historico.iniciar(tipo.id, tipo.nome, tema_final)

    scheduler.add_job(
        _job_reservado,
        trigger="date",
        run_date=datetime.now(),
        args=[tipo.id, tema_final, execucao],
        id=f"manual-{execucao['id']}",
    )
    return execucao


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
