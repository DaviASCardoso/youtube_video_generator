from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

from config.tipos import TipoVideo, listar_tipos_ativos, carregar_tipo
from config.sistema import sistema
from operacoes import recuperacao, saude
from descoberta import estado
from descoberta.configuracao import mesclar_descoberta
from descoberta.descoberta import decidir_tema
from operacoes.execucoes import (
    ExecucaoEmAndamentoError,
    definir_reagendador,
    executar_com_captura,
    historico,
    pasta_da_execucao,
    publicar_execucao,
    solicitar_cancelamento,
)

scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=sistema.get("execucao.max_simultaneo"))}
)

# Sufixo do id do job de descoberta de um tipo (o job de geração usa o id do tipo).
_SUFIXO_DESCOBERTA = "__descoberta"

# Job global de saúde: alerta (ntfy) sobre disco baixo / credencial expirando.
_ID_SAUDE = "__saude__"
_INTERVALO_SAUDE_HORAS = 6

# Job global do Feedback: ingere métricas (na agenda de maturação) e processa
# (findings + propostas) por tipo ativo. Inerte por default (destino de analytics
# desligado ⇒ nada é puxado nem proposto).
_ID_FEEDBACK = "__feedback__"
_INTERVALO_FEEDBACK_HORAS = 24

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


def _job_reservado(tipo_id: str, tema: str, execucao: dict, output_path=None) -> None:
    tipo = carregar_tipo(tipo_id)
    executar_com_captura(tema, tipo, execucao=execucao, output_path=output_path)


def _job_publicar(execucao_id: str) -> None:
    publicar_execucao(execucao_id)


def _reenfileirar_recuperado(tipo_id: str, tema: str, execucao: dict, output_path) -> None:
    """Re-enfileira um run órfão (reusa o registro e a pasta) no executor dos jobs."""
    scheduler.add_job(
        _job_reservado,
        trigger="date",
        run_date=datetime.now(),
        args=[tipo_id, tema, execucao, output_path],
        id=f"recuperado-{execucao['id']}",
        replace_existing=True,
    )


def _job_adiado(tipo_id: str, tema: str, output_path) -> None:
    """Retoma um run que foi adiado (cota/orçamento) quando a janela chega. Cria um
    novo registro e reusa a pasta antiga — o checkpoint pula os estágios já prontos."""
    tipo = carregar_tipo(tipo_id)
    try:
        execucao = historico.iniciar(tipo.id, tipo.nome, tema)
    except ExecucaoEmAndamentoError:
        print(f"[{tipo.nome}] Já há execução em andamento; run adiado não reenfileirado.")
        return
    executar_com_captura(tema, tipo, execucao=execucao, output_path=output_path)


def reagendar_adiado(tipo: TipoVideo, tema: str, output_path, quando: datetime) -> None:
    """Reprograma um run adiado para `quando` (a janela em que o recurso reseta),
    reusando a mesma pasta. Injetado no `executar_com_captura` via `definir_reagendador`."""
    scheduler.add_job(
        _job_adiado,
        trigger="date",
        run_date=quando,
        args=[tipo.id, tema, str(output_path)],
        id=f"adiado-{tipo.id}-{int(quando.timestamp())}",
        replace_existing=True,
    )


def _job_saude() -> None:
    """Check periódico de saúde: emite ntfy para disco baixo / credencial expirando."""
    try:
        saude.verificar_e_alertar()
    except Exception as e:  # noqa: BLE001
        print(f"[saude] falha no check periódico: {e}")


def _job_feedback() -> None:
    """Passada diária do Feedback: por tipo ativo, ingere métricas e processa findings/
    propostas. Degrada por tipo (uma falha não interrompe os demais) e é inerte quando o
    destino de analytics está desligado."""
    from feedback import ingestao, feedback as orquestrador

    for tipo in listar_tipos_ativos():
        try:
            ingestao.ingerir(tipo)
            orquestrador.processar(tipo)
        except Exception as e:  # noqa: BLE001
            print(f"[feedback] falha ao processar '{tipo.id}': {e}")


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


def descobrir_agora(tipo: TipoVideo) -> None:
    """Roda um ciclo de descoberta (só decisão do tema) agora, no mesmo executor dos
    jobs de cron — o "Descobrir agora" do painel. O resultado vai para o slot do tipo
    (pronto, ou pendente se em modo revisão)."""
    scheduler.add_job(
        _job_descoberta,
        trigger="date",
        run_date=datetime.now(),
        args=[tipo.id],
        id=f"descoberta-manual-{tipo.id}",
        replace_existing=True,
    )


def cancelar(execucao_id: str) -> None:
    """Pede o cancelamento cooperativo de uma execução. O pipeline aborta na próxima
    fronteira de estágio (um run já iniciado numa etapa longa só para ao terminá-la;
    um run ainda na fila aborta assim que começa)."""
    solicitar_cancelamento(execucao_id)


def reexecutar_agora(execucao_id: str) -> dict:
    """Reexecuta uma execução antiga reaproveitando a pasta do run (checkpoint):
    os estágios que já produziram artefato válido são pulados, e a geração retoma
    de onde parou. Roda no mesmo executor/teto de concorrência dos demais.

    Raises:
        ValueError: Se a execução original não tem uma pasta de run localizável.
        ExecucaoEmAndamentoError: Se já existe uma execução em andamento para o tipo.
    """
    registro = historico.obter(execucao_id)
    pasta = pasta_da_execucao(registro)
    if pasta is None:
        raise ValueError("Execução original não tem pasta de run para reaproveitar.")

    tipo = carregar_tipo(registro["tipo_id"])
    execucao = historico.iniciar(tipo.id, tipo.nome, registro["tema"])
    scheduler.add_job(
        _job_reservado,
        trigger="date",
        run_date=datetime.now(),
        args=[tipo.id, registro["tema"], execucao, str(pasta)],
        id=f"reexec-{execucao['id']}",
    )
    return execucao


def publicar_agora(execucao_id: str) -> None:
    """Dispara a publicação/reconciliação de uma execução no mesmo executor dos jobs
    (o botão "Aprovar & publicar"/"Republicar" do painel). Roda em background para a
    requisição HTTP retornar sem esperar o upload."""
    scheduler.add_job(
        _job_publicar,
        trigger="date",
        run_date=datetime.now(),
        args=[execucao_id],
        id=f"publicar-{execucao_id}",
        replace_existing=True,
    )


def atualizar_max_simultaneo(max_simultaneo: int) -> None:
    """Aplica uma mudança de execucao.max_simultaneo ao pool de execução em tempo real,
    sem precisar reiniciar o processo."""
    scheduler.remove_executor("default")
    scheduler.add_executor(ThreadPoolExecutor(max_workers=max_simultaneo), "default")


def iniciar() -> None:
    definir_reagendador(reagendar_adiado)  # runs adiados voltam pela janela de reset
    recuperacao.recuperar_execucoes(_reenfileirar_recuperado)  # retoma órfãos de um reboot
    for tipo in listar_tipos_ativos():
        registrar_job(tipo)
    scheduler.add_job(
        _job_saude,
        trigger="interval",
        hours=_INTERVALO_SAUDE_HORAS,
        id=_ID_SAUDE,
        replace_existing=True,
    )
    scheduler.add_job(
        _job_feedback,
        trigger="interval",
        hours=_INTERVALO_FEEDBACK_HORAS,
        id=_ID_FEEDBACK,
        replace_existing=True,
    )
    scheduler.start()


def parar() -> None:
    scheduler.shutdown(wait=False)
