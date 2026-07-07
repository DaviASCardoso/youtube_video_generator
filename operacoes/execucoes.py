from pathlib import Path
from datetime import datetime, timedelta, timezone
from queue import SimpleQueue
from uuid import uuid4
import json
import sys
import threading

from config.tipos import TipoVideo
from config.sistema import sistema
from geracao.custo import Ledger
from geracao.pipeline import gerar_video, ExecucaoCancelada, OrcamentoExcedido
from operacoes import notificacoes, resiliencia

_HISTORICO_PATH = Path(__file__).parent.parent / "execucoes" / "historico.json"


class ExecucaoEmAndamentoError(RuntimeError):
    """Levantado ao tentar iniciar uma execução para um tipo que já está em execução."""


class HistoricoExecucoes:
    """Histórico de execuções do pipeline, persistido em um historico.json.
    Mais recentes primeiro.
    """

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)
        self._lock = threading.Lock()

    def _carregar(self) -> list[dict]:
        if not self._caminho.exists():
            self._caminho.parent.mkdir(parents=True, exist_ok=True)
            self._caminho.write_text("[]", encoding="utf-8")
            return []

        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{self._caminho.name} inválido: {e}") from e

        if not isinstance(dados, list):
            raise ValueError(f"{self._caminho.name} deve ser uma lista.")

        return dados

    def _salvar(self, execucoes: list[dict]) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(execucoes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def em_execucao(self, tipo_id: str) -> bool:
        """Indica se já existe uma execução com status "executando" para esse tipo."""
        with self._lock:
            execucoes = self._carregar()
            return any(e["tipo_id"] == tipo_id and e["status"] == "executando" for e in execucoes)

    def iniciar(self, tipo_id: str, tipo_nome: str, tema: str) -> dict:
        """Registra o início de uma execução.

        A checagem "já em execução" e a inserção do novo registro acontecem sob o
        mesmo lock, para não haver corrida entre dois disparos quase simultâneos
        do mesmo tipo (ex: cron e "executar agora" ao mesmo tempo).

        Args:
            tipo_id: Id do tipo de vídeo.
            tipo_nome: Nome do tipo no momento da execução (fica congelado no registro).
            tema: Tema do vídeo sendo gerado.

        Returns:
            O registro de execução criado.

        Raises:
            ExecucaoEmAndamentoError: Se já existir uma execução em andamento para o tipo.
        """
        with self._lock:
            execucoes = self._carregar()
            if any(e["tipo_id"] == tipo_id and e["status"] == "executando" for e in execucoes):
                raise ExecucaoEmAndamentoError(
                    f"Já existe uma execução em andamento para o tipo '{tipo_id}'."
                )

            registro = {
                "id": uuid4().hex,
                "tipo_id": tipo_id,
                "tipo_nome": tipo_nome,
                "tema": tema,
                "status": "executando",
                "iniciado_em": datetime.now(timezone.utc).isoformat(),
                "finalizado_em": None,
                "output_path": None,
                "log_path": None,
                "url_publicacao": None,
                "publicacao": [],
                "custo_total": None,
                "custos": [],
                "provedores": {},
                "erro": None,
                # Observabilidade do motor de resiliência (Pilar 6).
                "retentativas": 0,
                "failover": False,
                "classe": None,
                "adiado_para": None,
                "recuperado": False,
            }
            execucoes.insert(0, registro)
            self._salvar(execucoes)
            return registro

    def _atualizar(self, execucao_id: str, **campos) -> dict:
        with self._lock:
            execucoes = self._carregar()
            for execucao in execucoes:
                if execucao["id"] == execucao_id:
                    execucao.update(campos)
                    self._salvar(execucoes)
                    return execucao
            raise KeyError(f"Execução '{execucao_id}' não encontrada.")

    def definir_log_path(self, execucao_id: str, log_path: Path) -> dict:
        return self._atualizar(execucao_id, log_path=str(log_path))

    def registrar_publicacao(self, execucao_id: str, url: str) -> dict:
        return self._atualizar(execucao_id, url_publicacao=str(url))

    def registrar_publicacao_destino(self, execucao_id: str, destino: str, dados: dict) -> dict:
        """Grava (upsert) o published-record de um destino: id/url/quota/visibilidade/
        status etc. É a base da idempotência — um destino já publicado não sobe de novo.

        Mantém `url_publicacao` (usado nos templates) apontando para a primeira URL
        publicada com sucesso.
        """
        with self._lock:
            execucoes = self._carregar()
            for execucao in execucoes:
                if execucao["id"] == execucao_id:
                    lista = execucao.setdefault("publicacao", [])
                    registro = {"destino": destino, **dados}
                    for i, item in enumerate(lista):
                        if item.get("destino") == destino:
                            lista[i] = registro
                            break
                    else:
                        lista.append(registro)
                    if dados.get("url") and not execucao.get("url_publicacao"):
                        execucao["url_publicacao"] = dados["url"]
                    self._salvar(execucoes)
                    return execucao
            raise KeyError(f"Execução '{execucao_id}' não encontrada.")

    def publicacao_de(self, execucao_id: str, destino: str) -> dict | None:
        """Published-record de um destino, ou None se ainda não houver. Usado para
        reconciliar um retry: se já existe id, não republica."""
        for execucao in self._carregar():
            if execucao["id"] == execucao_id:
                for item in execucao.get("publicacao", []):
                    if item.get("destino") == destino:
                        return item
                return None
        raise KeyError(f"Execução '{execucao_id}' não encontrada.")

    def marcar_aguardando_publicacao(self, execucao_id: str) -> dict:
        """Gate de revisão: o vídeo está pronto mas aguarda aprovação humana para ir
        ao ar. Terminal do lado da geração; a publicação acontece quando aprovado."""
        return self._atualizar(
            execucao_id,
            status="aguardando_publicacao",
            finalizado_em=datetime.now(timezone.utc).isoformat(),
        )

    def rejeitar_publicacao(self, execucao_id: str) -> dict:
        """Gate de revisão: rejeita a publicação de um run que aguardava aprovação.
        O vídeo continua no disco; o run sai da fila de aprovação como 'rejeitado'."""
        return self._atualizar(
            execucao_id,
            status="rejeitado",
            finalizado_em=datetime.now(timezone.utc).isoformat(),
        )

    def registrar_custos(self, execucao_id: str, ledger) -> dict:
        """Anota no registro o custo/provedor por etapa vindos do Ledger do run."""
        return self._atualizar(
            execucao_id,
            custo_total=round(ledger.total(), 6),
            custos=ledger.itens(),
            provedores=ledger.provedores(),
        )

    def concluir(self, execucao_id: str, output_path: Path) -> dict:
        return self._atualizar(
            execucao_id,
            status="concluido",
            finalizado_em=datetime.now(timezone.utc).isoformat(),
            output_path=str(output_path),
        )

    def falhar(self, execucao_id: str, erro: str) -> dict:
        return self._atualizar(
            execucao_id,
            status="erro",
            finalizado_em=datetime.now(timezone.utc).isoformat(),
            erro=erro,
        )

    def cancelar(self, execucao_id: str) -> dict:
        return self._atualizar(
            execucao_id,
            status="cancelado",
            finalizado_em=datetime.now(timezone.utc).isoformat(),
        )

    def registrar_resiliencia(self, execucao_id: str, relatorio: dict) -> dict:
        """Anota a observabilidade do motor no run: nº de retentativas, se houve
        failover e as classes de erro vistas ao longo dos estágios."""
        classes = relatorio.get("classes") or []
        return self._atualizar(
            execucao_id,
            retentativas=int(relatorio.get("tentativas", 0)),
            failover=bool(relatorio.get("failover", False)),
            classe=classes[-1] if classes else None,
        )

    def marcar_adiado(self, execucao_id: str, classe: str, adiado_para: str, erro: str) -> dict:
        """Defer-para-janela: o recurso (cota/orçamento) estourou; o run é reprogramado
        para quando ele reseta. Registrado (nunca perdido) com a classe e o horário-alvo."""
        return self._atualizar(
            execucao_id,
            status="adiado",
            finalizado_em=datetime.now(timezone.utc).isoformat(),
            classe=classe,
            adiado_para=adiado_para,
            erro=erro,
        )

    def marcar_dead_letter(self, execucao_id: str, classe: str, erro: str) -> dict:
        """Dead-letter: as estratégias casadas se esgotaram. Terminal, escalado e
        re-executável pelo painel — a razão classificada fica registrada."""
        return self._atualizar(
            execucao_id,
            status="dead_letter",
            finalizado_em=datetime.now(timezone.utc).isoformat(),
            classe=classe,
            erro=erro,
        )

    def marcar_recuperado(self, execucao_id: str) -> dict:
        """Marca que este run foi retomado após um reinício (recuperação de crash)."""
        return self._atualizar(execucao_id, recuperado=True)

    def listar(self, tipo_id: str | None = None) -> list[dict]:
        """Lista execuções, mais recentes primeiro.

        Args:
            tipo_id: Se informado, filtra apenas execuções desse tipo.
        """
        execucoes = self._carregar()
        if tipo_id is not None:
            execucoes = [e for e in execucoes if e["tipo_id"] == tipo_id]
        return execucoes

    def obter(self, execucao_id: str) -> dict:
        for execucao in self._carregar():
            if execucao["id"] == execucao_id:
                return execucao
        raise KeyError(f"Execução '{execucao_id}' não encontrada.")

    def migrar_tipo_id(self, id_antigo: str, novo_id: str) -> None:
        """Atualiza o tipo_id de execuções antigas após um tipo ser renomeado.

        O tipo_nome de cada registro não é alterado — continua sendo o nome
        de exibição válido no momento em que aquela execução aconteceu.
        """
        with self._lock:
            execucoes = self._carregar()
            alterado = False
            for execucao in execucoes:
                if execucao["tipo_id"] == id_antigo:
                    execucao["tipo_id"] = novo_id
                    alterado = True
            if alterado:
                self._salvar(execucoes)


historico = HistoricoExecucoes(_HISTORICO_PATH)

# Cancelamento cooperativo: o painel pede o cancelamento de uma execução em curso e o
# pipeline aborta na próxima fronteira de estágio (não há como matar uma etapa longa).
_cancelamentos: set[str] = set()
_cancel_lock = threading.Lock()


def solicitar_cancelamento(execucao_id: str) -> None:
    with _cancel_lock:
        _cancelamentos.add(execucao_id)


def cancelamento_pedido(execucao_id: str) -> bool:
    with _cancel_lock:
        return execucao_id in _cancelamentos


def _limpar_cancelamento(execucao_id: str) -> None:
    with _cancel_lock:
        _cancelamentos.discard(execucao_id)


# Reagendador de runs adiados (defer-para-janela). O scheduler injeta o seu na subida
# (`definir_reagendador`); sem ele, um defer só marca 'adiado' (nada reagenda) —
# assim a orquestração fica desacoplada do scheduler e testável sem um em execução.
_reagendador = None


def definir_reagendador(fn) -> None:
    """Registra a função que reprograma um run adiado — `(tipo, tema, output_path,
    quando: datetime) -> None`. Chamada pelo scheduler na subida."""
    global _reagendador
    _reagendador = fn


def pasta_da_execucao(registro: dict) -> Path | None:
    """Pasta do run de uma execução antiga, para reexecutar reaproveitando o
    checkpoint. `output_path` guarda o video_final.mp4 (a pasta é o pai); num run
    que falhou antes do vídeo, cai no diretório do log."""
    if registro.get("output_path"):
        return Path(registro["output_path"]).parent
    if registro.get("log_path"):
        return Path(registro["log_path"]).parent
    return None


class _TransmissorLog:
    """Mantém, em memória, o log ao vivo de cada execução em andamento e
    distribui novas linhas para assinantes (usado pelo endpoint SSE).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._linhas: dict[str, list[str]] = {}
        self._assinantes: dict[str, list[SimpleQueue]] = {}

    def registrar_linha(self, execucao_id: str, linha: str) -> None:
        with self._lock:
            self._linhas.setdefault(execucao_id, []).append(linha)
            for fila in self._assinantes.get(execucao_id, []):
                fila.put(linha)

    def encerrar(self, execucao_id: str) -> None:
        with self._lock:
            for fila in self._assinantes.get(execucao_id, []):
                fila.put(None)  # sentinela: fim do stream
            self._assinantes.pop(execucao_id, None)
            self._linhas.pop(execucao_id, None)

    def linhas_ate_agora(self, execucao_id: str) -> list[str]:
        with self._lock:
            return list(self._linhas.get(execucao_id, []))

    def assinar(self, execucao_id: str) -> SimpleQueue:
        fila = SimpleQueue()
        with self._lock:
            self._assinantes.setdefault(execucao_id, []).append(fila)
        return fila

    def desassinar(self, execucao_id: str, fila: SimpleQueue) -> None:
        with self._lock:
            assinantes = self._assinantes.get(execucao_id, [])
            if fila in assinantes:
                assinantes.remove(fila)


transmissor = _TransmissorLog()


class _TeeStdout:
    """Escreve em um arquivo de log da execução e envia linhas completas ao transmissor."""

    def __init__(self, execucao_id: str, log_path: Path):
        self._execucao_id = execucao_id
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._arquivo = log_path.open("a", encoding="utf-8")
        self._buffer = ""

    def write(self, texto: str) -> int:
        self._arquivo.write(texto)
        self._arquivo.flush()
        self._buffer += texto
        while "\n" in self._buffer:
            linha, self._buffer = self._buffer.split("\n", 1)
            transmissor.registrar_linha(self._execucao_id, linha)
        return len(texto)

    def flush(self) -> None:
        self._arquivo.flush()

    def close(self) -> None:
        if self._buffer:
            transmissor.registrar_linha(self._execucao_id, self._buffer)
            self._buffer = ""
        self._arquivo.close()
        transmissor.encerrar(self._execucao_id)


class _StdoutProxy:
    """Substitui sys.stdout uma única vez no processo. Escritas de uma thread
    com uma execução ativa vão para o log dessa execução; as demais (thread
    principal, outras threads sem execução ativa) seguem para o stdout real.

    Necessário porque contextlib.redirect_stdout troca sys.stdout globalmente
    e quebraria a captura ao ter mais de uma execução rodando ao mesmo tempo
    (execucao.max_simultaneo > 1) — cada thread do agendador precisa do seu
    próprio destino.
    """

    def __init__(self, stdout_real):
        self._stdout_real = stdout_real
        self._local = threading.local()

    def _destino(self):
        return getattr(self._local, "tee", None) or self._stdout_real

    def write(self, texto: str) -> int:
        return self._destino().write(texto)

    def flush(self) -> None:
        self._destino().flush()

    def ativar(self, tee: _TeeStdout) -> None:
        self._local.tee = tee

    def desativar(self) -> None:
        self._local.tee = None

    def __getattr__(self, nome):
        # Encaminha tudo que não é escrita (isatty, fileno, encoding, ...) para o
        # stdout real — essas são propriedades do terminal, não do destino da escrita.
        return getattr(self._stdout_real, nome)


if not isinstance(sys.stdout, _StdoutProxy):
    sys.stdout = _StdoutProxy(sys.stdout)

_proxy: _StdoutProxy = sys.stdout


def _publicar_se_configurado(execucao_id: str, tipo: TipoVideo, caminho_video: Path, ledger=None) -> str:
    """Delega ao Pilar de Publicação (metadados Groq → thumbnail → destinos).

    Roda dentro da captura de log (aparece no log ao vivo). Uma falha global é
    registrada mas NÃO derruba a execução — o vídeo já foi gerado e continua no
    disco. Devolve o desfecho (ver `publicador.publicar`): "sem_destino",
    "aguardando_revisao" ou "publicado".
    """
    # import tardio: só puxa Publicação (e as libs do Google) quando o run termina
    from publicacao import publicador

    try:
        return publicador.publicar(tipo, Path(caminho_video).parent, execucao_id, ledger=ledger)
    except Exception as e:  # noqa: BLE001
        print(f"AVISO: publicação falhou (o vídeo foi gerado normalmente): {e}")
        return "erro"


def executar_com_captura(
    tema: str,
    tipo: TipoVideo,
    execucao: dict | None = None,
    output_path: Path | None = None,
) -> Path:
    """Executa o pipeline para um tema/tipo, registrando histórico e log da execução.

    Ponto de entrada único usado tanto pelo agendador (cron) quanto por disparos
    manuais via API, garantindo que ambos os caminhos produzam o mesmo histórico
    e o mesmo log ao vivo.

    Args:
        tema: Tema do vídeo a gerar.
        tipo: Tipo de vídeo a usar na geração.
        execucao: Registro de histórico já criado (via historico.iniciar), para quando
            o chamador precisa saber o id da execução antes do trabalho pesado começar
            (ex: disparo manual pela API). Se None, o registro é criado aqui.

    Returns:
        Path do vídeo final gerado.

    Raises:
        ExecucaoEmAndamentoError: Se já existir uma execução em andamento para esse tipo
            (apenas quando `execucao` não é informado).
    """
    if execucao is None:
        execucao = historico.iniciar(tipo.id, tipo.nome, tema)
    if output_path is None:
        # Run novo: pasta com timestamp. Reexecutar passa a pasta antiga, e aí o
        # checkpoint do pipeline reaproveita os artefatos que já existem e validam.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(sistema.get("saida.pasta_base")) / tipo.id / timestamp
    output_path = Path(output_path)
    log_path = output_path / "execucao.log"
    historico.definir_log_path(execucao["id"], log_path)

    tee = _TeeStdout(execucao["id"], log_path)
    _proxy.ativar(tee)
    ledger = Ledger()
    rel: dict = {}  # observabilidade do motor: retentativas/failover/classes
    try:
        caminho = gerar_video(
            tema=tema, tipo=tipo, output_path=output_path, ledger=ledger,
            cancelado=lambda: cancelamento_pedido(execucao["id"]),
            relatorio=rel,
        )
        historico.registrar_custos(execucao["id"], ledger)
        historico.registrar_resiliencia(execucao["id"], rel)
        _publicar_se_configurado(execucao["id"], tipo, caminho, ledger=ledger)
        # A publicação pode ter marcado o run como "aguardando_publicacao" (gate de
        # revisão); só concluímos se ela não moveu o status.
        if historico.obter(execucao["id"])["status"] == "executando":
            historico.concluir(execucao["id"], caminho)
        return caminho
    except ExecucaoCancelada:
        print("Execução cancelada pelo usuário.")
        historico.registrar_resiliencia(execucao["id"], rel)
        historico.cancelar(execucao["id"])
        raise
    except (resiliencia.Deferir, OrcamentoExcedido) as e:
        historico.registrar_resiliencia(execucao["id"], rel)
        _adiar_execucao(execucao, tipo, tema, output_path, e)
        raise
    except (resiliencia.ResilienciaEsgotada, resiliencia.HaltDestino) as e:
        classe = getattr(e, "classe", "auth")
        historico.registrar_resiliencia(execucao["id"], rel)
        historico.marcar_dead_letter(execucao["id"], classe, str(e))
        notificacoes.emitir(
            "job_dead_letter",
            f"Dead-letter — {tipo.nome}",
            f"Tema: {tema}\nClasse: {classe}\n{e}",
        )
        raise
    except Exception as e:
        historico.registrar_resiliencia(execucao["id"], rel)
        historico.falhar(execucao["id"], str(e))
        notificacoes.emitir(
            "run_falhou",
            f"Falha na geração — {tipo.nome}",
            f"Tema: {tema}\n{e}",
        )
        raise
    finally:
        _limpar_cancelamento(execucao["id"])
        _proxy.desativar()
        tee.close()


def _adiar_execucao(execucao: dict, tipo: TipoVideo, tema: str, output_path: Path, erro: Exception) -> None:
    """Marca o run como 'adiado' e o reprograma para a janela em que o recurso reseta.

    `Deferir` traz a janela em horas; `OrcamentoExcedido` usa o `defer_horas.orcamento`
    do tipo. Reusa a mesma pasta (o checkpoint retoma os estágios já prontos). Se não há
    reagendador injetado (scheduler fora do ar), o run fica registrado como 'adiado'
    mesmo assim — nunca é perdido em silêncio."""
    politica = resiliencia.de_tipo(tipo)
    if isinstance(erro, resiliencia.Deferir):
        classe, horas = erro.classe, erro.quando_horas
    else:  # OrcamentoExcedido
        classe, horas = "orcamento", politica.defer_horas.get("orcamento", 24)
    quando = datetime.now() + timedelta(hours=float(horas))
    historico.marcar_adiado(execucao["id"], classe, quando.astimezone().isoformat(), str(erro))
    print(f"Execução adiada ({classe}) para {quando.isoformat()} — recurso esgotado.")
    notificacoes.emitir(
        "cota_atingida",
        f"Execução adiada — {tipo.nome}",
        f"Tema: {tema}\nClasse: {classe}\nReprogramada para {quando.strftime('%d/%m %H:%M')}.",
    )
    if _reagendador is not None:
        _reagendador(tipo, tema, Path(output_path), quando)


def publicar_execucao(execucao_id: str) -> str:
    """Publica (ou reconcilia) uma execução já gerada — o caminho do botão "Aprovar &
    publicar" do gate de revisão e do "Republicar" após falha parcial. Reaproveita os
    metadados/thumbnail já checkpointados; idempotente por destino. Captura o log na
    mesma `execucao.log` do run. Devolve o desfecho de `publicador.publicar_aprovado`.
    """
    from publicacao import publicador

    registro_exec = historico.obter(execucao_id)
    pasta = pasta_da_execucao(registro_exec)
    log_path = (
        Path(registro_exec["log_path"]) if registro_exec.get("log_path")
        else (pasta / "execucao.log" if pasta else None)
    )
    if log_path is None:
        raise ValueError("Execução sem pasta/log para publicar.")

    tee = _TeeStdout(execucao_id, log_path)
    _proxy.ativar(tee)
    try:
        print("\nPublicando (aprovação/reconciliação)...")
        return publicador.publicar_aprovado(execucao_id)
    finally:
        _proxy.desativar()
        tee.close()
