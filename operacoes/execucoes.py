from pathlib import Path
from datetime import datetime, timezone
from queue import SimpleQueue
from uuid import uuid4
import json
import sys
import threading

from config.tipos import TipoVideo
from config.sistema import sistema
from geracao import sidecar
from geracao.custo import Ledger
from geracao.pipeline import gerar_video

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
                "custo_total": None,
                "custos": [],
                "provedores": {},
                "erro": None,
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


def _publicar_se_configurado(execucao_id: str, tema: str, tipo: TipoVideo, caminho_video: Path) -> None:
    """Publica o vídeo no YouTube se o tipo tiver youtube.publicar ligado.

    Roda dentro da captura de log (aparece no log ao vivo). Uma falha de
    publicação é registrada mas NÃO derruba a execução — o vídeo já foi gerado
    e continua no disco para publicar manualmente depois.
    """
    try:
        publicar = tipo.config.get("youtube.publicar")
    except KeyError:
        return  # tipos antigos, sem o campo
    if not publicar:
        return

    # import tardio: só puxa as libs do Google quando realmente vai publicar
    from publicacao import youtube

    try:
        # Handoff pela Geração: o sidecar traz o roteiro; se faltar, cai no roteiro.txt.
        base = Path(caminho_video).parent
        registro = sidecar.ler(base) or {}
        roteiro = registro.get("roteiro")
        if roteiro is None:
            roteiro_path = base / "roteiro.txt"
            roteiro = roteiro_path.read_text(encoding="utf-8") if roteiro_path.exists() else ""
        print("\nPublicando no YouTube...")
        url = youtube.publicar_video(caminho_video, tema, tipo, roteiro)
        historico.registrar_publicacao(execucao_id, url)
    except Exception as e:
        print(f"AVISO: publicação no YouTube falhou (o vídeo foi gerado normalmente): {e}")


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
    try:
        caminho = gerar_video(tema=tema, tipo=tipo, output_path=output_path, ledger=ledger)
        historico.registrar_custos(execucao["id"], ledger)
        _publicar_se_configurado(execucao["id"], tema, tipo, caminho)
        historico.concluir(execucao["id"], caminho)
        return caminho
    except Exception as e:
        historico.falhar(execucao["id"], str(e))
        raise
    finally:
        _proxy.desativar()
        tee.close()
