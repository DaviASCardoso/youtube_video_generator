import pytest

from operacoes import scheduler as sched
from descoberta import estado
from descoberta.candidato import Decisao


def _campos(trigger):
    return {f.name: str(f) for f in trigger.fields}


def _decisao(estado_gate="pronto", tema="Tema"):
    return Decisao(
        tema=tema,
        fonte="reddit",
        categoria="trending",
        fit_score=80.0,
        justificativa="j",
        prioridade=0.6,
        estado=estado_gate,
    )


def _agendamento(freq, horario="02:00"):
    return {"agendamento": {"frequencia": freq, "horario": horario, "fuso_horario": "America/Sao_Paulo"}}


# --- _trigger_descoberta (X horas antes) ---

def test_trigger_descoberta_diario(make_tipo):
    tipo = make_tipo(config_extra=_agendamento("daily"))
    campos = _campos(sched._trigger_descoberta(tipo, 6))
    assert campos["hour"] == "20"  # 02:00 - 6h = 20:00 (dia anterior)
    assert campos["minute"] == "0"


def test_trigger_descoberta_semanal_vira_o_dia(make_tipo):
    tipo = make_tipo(config_extra=_agendamento("weekly"))
    campos = _campos(sched._trigger_descoberta(tipo, 6))
    # segunda 02:00 - 6h = domingo 20:00
    assert "sun" in campos["day_of_week"]
    assert campos["hour"] == "20"


def test_trigger_descoberta_mensal_limita_dia(make_tipo):
    tipo = make_tipo(config_extra=_agendamento("monthly"))
    campos = _campos(sched._trigger_descoberta(tipo, 6))
    assert campos["day"] == "28"  # dia 1 - 6h cairia no fim do mês, limitado a 28
    assert campos["hour"] == "20"


# --- _job_agendado (consome o slot decidido) ---

def test_job_agendado_gera_do_slot_pronto(make_tipo, monkeypatch):
    tipo = make_tipo()  # antecedencia padrão 2 (>0): sem descoberta inline
    estado.slot_de(tipo).gravar(_decisao(tema="Tema Slot"))
    chamou = {}
    monkeypatch.setattr(sched, "executar_com_captura", lambda tema, tipo, **k: chamou.setdefault("tema", tema))

    sched._job_agendado(tipo.id)
    assert chamou["tema"] == "Tema Slot"
    assert estado.slot_de(tipo).ler() is None  # slot limpo após consumir


def test_job_agendado_pula_pendente(make_tipo, monkeypatch):
    tipo = make_tipo()
    estado.slot_de(tipo).gravar(_decisao(estado_gate="pendente"))
    chamou = {}
    monkeypatch.setattr(sched, "executar_com_captura", lambda *a, **k: chamou.setdefault("x", True))

    sched._job_agendado(tipo.id)
    assert "x" not in chamou
    assert estado.slot_de(tipo).ler() is not None  # não consumiu


def test_job_agendado_pula_sem_slot(make_tipo, monkeypatch):
    tipo = make_tipo()
    chamou = {}
    monkeypatch.setattr(sched, "executar_com_captura", lambda *a, **k: chamou.setdefault("x", True))

    sched._job_agendado(tipo.id)
    assert "x" not in chamou


def test_job_agendado_antecedencia_zero_descobre_inline(make_tipo, monkeypatch):
    tipo = make_tipo(config_extra={"descoberta": {"antecedencia_horas": 0}})

    def _descobrir(tipo):
        estado.slot_de(tipo).gravar(_decisao(tema="Descoberto"))

    monkeypatch.setattr(sched, "decidir_tema", _descobrir)
    chamou = {}
    monkeypatch.setattr(sched, "executar_com_captura", lambda tema, tipo, **k: chamou.setdefault("tema", tema))

    sched._job_agendado(tipo.id)
    assert chamou["tema"] == "Descoberto"


# --- disparar_agora ---

@pytest.fixture
def sem_efeitos(monkeypatch):
    """Evita tocar no histórico real e no scheduler ao disparar."""
    monkeypatch.setattr(sched.historico, "iniciar", lambda tid, tn, tema: {"id": "1", "tema": tema})
    monkeypatch.setattr(sched.scheduler, "add_job", lambda *a, **k: None)


def test_disparar_com_tema_explicito(make_tipo, sem_efeitos):
    ex = sched.disparar_agora(make_tipo(), "Meu Tema")
    assert ex["tema"] == "Meu Tema"


def test_disparar_consome_slot_pronto(make_tipo, sem_efeitos):
    tipo = make_tipo()
    estado.slot_de(tipo).gravar(_decisao(tema="Do Slot"))
    ex = sched.disparar_agora(tipo)
    assert ex["tema"] == "Do Slot"
    assert estado.slot_de(tipo).ler() is None


def test_disparar_sem_slot_roda_descoberta(make_tipo, sem_efeitos, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(sched, "decidir_tema", lambda tipo: _decisao(tema="Novo"))
    ex = sched.disparar_agora(tipo)
    assert ex["tema"] == "Novo"


def test_disparar_pendente_erra(make_tipo, sem_efeitos, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(sched, "decidir_tema", lambda tipo: _decisao(estado_gate="pendente"))
    with pytest.raises(ValueError):
        sched.disparar_agora(tipo)


def test_disparar_nada_encontrado_erra(make_tipo, sem_efeitos, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(sched, "decidir_tema", lambda tipo: None)
    with pytest.raises(ValueError):
        sched.disparar_agora(tipo)


# --- reexecutar_agora ---

def test_reexecutar_agora_reserva_com_pasta(make_tipo, monkeypatch):
    tipo = make_tipo()
    registro = {
        "id": "velho",
        "tipo_id": tipo.id,
        "tema": "Tema Antigo",
        "output_path": "output/x/2026/video_final.mp4",
        "log_path": None,
    }
    monkeypatch.setattr(sched.historico, "obter", lambda eid: registro)
    monkeypatch.setattr(
        sched.historico, "iniciar", lambda tid, tn, tema: {"id": "novo", "tema": tema}
    )
    capturado = {}
    monkeypatch.setattr(sched.scheduler, "add_job", lambda *a, **k: capturado.update(kwargs=k))

    ex = sched.reexecutar_agora("velho")
    assert ex["tema"] == "Tema Antigo"
    # a pasta do run antigo (pai do video_final.mp4) é passada ao job reservado
    from pathlib import Path

    assert Path(capturado["kwargs"]["args"][-1]) == Path("output/x/2026")


def test_reexecutar_agora_sem_pasta_erra(make_tipo, monkeypatch):
    tipo = make_tipo()
    registro = {"id": "v", "tipo_id": tipo.id, "tema": "t", "output_path": None, "log_path": None}
    monkeypatch.setattr(sched.historico, "obter", lambda eid: registro)
    with pytest.raises(ValueError):
        sched.reexecutar_agora("v")


# --- reagendar_adiado (defer-para-janela) ---

def test_reagendar_adiado_agenda_na_janela(make_tipo, monkeypatch):
    from datetime import datetime

    tipo = make_tipo()
    capturado = {}
    monkeypatch.setattr(sched.scheduler, "add_job", lambda *a, **k: capturado.update(kwargs=k))
    quando = datetime(2026, 7, 8, 6, 0, 0)

    sched.reagendar_adiado(tipo, "meu tema", "output/x/2026", quando)

    assert capturado["kwargs"]["run_date"] == quando
    assert capturado["kwargs"]["args"] == [tipo.id, "meu tema", "output/x/2026"]


def test_iniciar_injeta_reagendador(monkeypatch):
    monkeypatch.setattr(sched, "listar_tipos_ativos", lambda: [])
    monkeypatch.setattr(sched.scheduler, "add_job", lambda *a, **k: None)
    monkeypatch.setattr(sched.scheduler, "start", lambda: None)
    monkeypatch.setattr(sched.recuperacao, "recuperar_execucoes", lambda fn: [])
    registrado = {}
    monkeypatch.setattr(sched, "definir_reagendador", lambda fn: registrado.update(fn=fn))

    sched.iniciar()
    assert registrado["fn"] is sched.reagendar_adiado


def test_iniciar_recupera_orfaos(monkeypatch):
    monkeypatch.setattr(sched, "listar_tipos_ativos", lambda: [])
    monkeypatch.setattr(sched.scheduler, "add_job", lambda *a, **k: None)
    monkeypatch.setattr(sched.scheduler, "start", lambda: None)
    recebido = {}
    monkeypatch.setattr(
        sched.recuperacao, "recuperar_execucoes",
        lambda fn: recebido.update(enfileirar=fn) or [],
    )
    sched.iniciar()
    assert recebido["enfileirar"] is sched._reenfileirar_recuperado


def test_reenfileirar_recuperado_reserva_pasta(monkeypatch):
    capturado = {}
    monkeypatch.setattr(sched.scheduler, "add_job", lambda *a, **k: capturado.update(kwargs=k))
    sched._reenfileirar_recuperado("canal", "tema", {"id": "orf"}, "output/x/2026")
    assert capturado["kwargs"]["args"] == ["canal", "tema", {"id": "orf"}, "output/x/2026"]
    assert capturado["kwargs"]["id"] == "recuperado-orf"


# --- publicar_agora ---

def test_publicar_agora_agenda_job(monkeypatch):
    capturado = {}
    monkeypatch.setattr(sched.scheduler, "add_job", lambda *a, **k: capturado.update(kwargs=k))
    sched.publicar_agora("EX1")
    assert capturado["kwargs"]["args"] == ["EX1"]
    assert capturado["kwargs"]["id"] == "publicar-EX1"


# --- descobrir_agora / cancelar ---

def test_descobrir_agora_agenda_job(make_tipo, monkeypatch):
    capturado = {}
    monkeypatch.setattr(sched.scheduler, "add_job", lambda *a, **k: capturado.update(kwargs=k))
    tipo = make_tipo()
    sched.descobrir_agora(tipo)
    assert capturado["kwargs"]["args"] == [tipo.id]
    assert capturado["kwargs"]["id"] == f"descoberta-manual-{tipo.id}"


def test_cancelar_pede_cancelamento(monkeypatch):
    chamado = []
    monkeypatch.setattr(sched, "solicitar_cancelamento", lambda eid: chamado.append(eid))
    sched.cancelar("EXEC-9")
    assert chamado == ["EXEC-9"]


# --- _job_feedback (ingestão + processamento por tipo ativo) ---


def test_job_feedback_processa_cada_tipo_ativo(make_tipo, monkeypatch):
    from feedback import ingestao
    from feedback import feedback as orq

    t1 = make_tipo("t1")
    t2 = make_tipo("t2")
    monkeypatch.setattr(sched, "listar_tipos_ativos", lambda: [t1, t2])
    ingeridos, processados = [], []
    monkeypatch.setattr(ingestao, "ingerir", lambda tipo: ingeridos.append(tipo.id))
    monkeypatch.setattr(orq, "processar", lambda tipo: processados.append(tipo.id))

    sched._job_feedback()
    assert ingeridos == ["t1", "t2"]
    assert processados == ["t1", "t2"]


def test_job_feedback_degrada_por_tipo(make_tipo, monkeypatch):
    from feedback import ingestao
    from feedback import feedback as orq

    t1 = make_tipo("t1")
    t2 = make_tipo("t2")
    monkeypatch.setattr(sched, "listar_tipos_ativos", lambda: [t1, t2])

    def _ingerir(tipo):
        if tipo.id == "t1":
            raise RuntimeError("estourou t1")

    processados = []
    monkeypatch.setattr(ingestao, "ingerir", _ingerir)
    monkeypatch.setattr(orq, "processar", lambda tipo: processados.append(tipo.id))

    sched._job_feedback()  # não levanta
    assert processados == ["t2"]  # t1 falhou na ingestão, t2 seguiu
