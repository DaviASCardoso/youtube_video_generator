"""Estado por tipo da Descoberta: slot decidido, buffer de retenção, histórico.

Três arquivos por tipo, no mesmo padrão de FilaDeTemas/HistoricoExecucoes (JSON
plano protegido por threading.Lock), todos gitignored (runtime):

  descoberta_slot.json       o único tema decidido (Decisao) + estado pronto/pendente
  descoberta_buffer.json     candidatos avaliados e retidos (modo "reter"), com fit_score
  descoberta_historico.json  observabilidade por run + os temas decididos (dedup/balanço)

O pool de ideias manuais/evergreen NÃO vive aqui: continua no temas.json do tipo
(FilaDeTemas), lido pela fonte `pool`, distinguido pelo campo `fonte`.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from descoberta.candidato import Candidato, Decisao
from descoberta.tendencias import _normalizar


class _ArquivoJson:
    """Base: carrega/salva um JSON num caminho, protegido por lock."""

    def __init__(self, caminho: Path, vazio):
        self._caminho = Path(caminho)
        self._lock = threading.Lock()
        self._vazio = vazio

    def _carregar(self):
        if not self._caminho.exists():
            return json.loads(json.dumps(self._vazio))
        try:
            return json.loads(self._caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{self._caminho.name} inválido: {e}") from e

    def _salvar(self, dados) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class SlotDecidido(_ArquivoJson):
    """O único tema decidido do tipo (ou nada)."""

    def __init__(self, caminho: Path):
        super().__init__(caminho, None)

    def ler(self) -> Decisao | None:
        with self._lock:
            dados = self._carregar()
        return Decisao.de_dict(dados) if dados else None

    def gravar(self, decisao: Decisao) -> None:
        with self._lock:
            self._salvar(decisao.para_dict())

    def aprovar(self) -> Decisao | None:
        """Marca a decisão pendente como pronta (gate de revisão). Devolve-a."""
        with self._lock:
            dados = self._carregar()
            if not dados:
                return None
            dados["estado"] = "pronto"
            self._salvar(dados)
            return Decisao.de_dict(dados)

    def limpar(self) -> None:
        with self._lock:
            self._salvar(None)


class BufferRetencao(_ArquivoJson):
    """Candidatos avaliados e retidos entre ciclos (modo "reter")."""

    def __init__(self, caminho: Path):
        super().__init__(caminho, [])

    def listar(self) -> list[Candidato]:
        with self._lock:
            dados = self._carregar()
        return [Candidato.de_dict(d) for d in dados]

    def substituir(self, candidatos: list[Candidato]) -> None:
        with self._lock:
            self._salvar([c.para_dict() for c in candidatos])

    def limpar(self) -> None:
        with self._lock:
            self._salvar([])


class HistoricoDescoberta(_ArquivoJson):
    """Observabilidade por run + registro dos temas decididos (dedup/balanço)."""

    def __init__(self, caminho: Path):
        super().__init__(caminho, [])

    def registrar(self, registro: dict) -> dict:
        registro = {"quando": datetime.now(timezone.utc).isoformat(), **registro}
        with self._lock:
            dados = self._carregar()
            dados.insert(0, registro)
            self._salvar(dados)
        return registro

    def listar(self) -> list[dict]:
        with self._lock:
            return self._carregar()

    def categorias_recentes(self, n: int) -> list[str]:
        """Categorias dos últimos `n` temas decididos (mais recente primeiro)."""
        categorias = []
        for r in self.listar():
            decidido = r.get("decidido")
            if decidido and decidido.get("categoria"):
                categorias.append(decidido["categoria"])
            if len(categorias) >= n:
                break
        return categorias

    def temas_decididos_recentes(self, dias: int) -> set[str]:
        """Temas decididos (normalizados) nos últimos `dias` — para o dedupe."""
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        recentes = set()
        for r in self.listar():
            decidido = r.get("decidido")
            if not decidido or not decidido.get("tema"):
                continue
            try:
                quando = datetime.fromisoformat(r["quando"])
            except (KeyError, ValueError):
                continue
            if quando >= limite:
                recentes.add(_normalizar(decidido["tema"]))
        return recentes


def slot_de(tipo) -> SlotDecidido:
    return SlotDecidido(tipo.caminho / "descoberta_slot.json")


def buffer_de(tipo) -> BufferRetencao:
    return BufferRetencao(tipo.caminho / "descoberta_buffer.json")


def historico_de(tipo) -> HistoricoDescoberta:
    return HistoricoDescoberta(tipo.caminho / "descoberta_historico.json")
