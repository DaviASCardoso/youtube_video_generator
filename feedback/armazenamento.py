"""Stores por tipo do Feedback: métricas, findings, propostas e aplicados.

Quatro arquivos por tipo, no mesmo padrão de `descoberta.estado`/`FilaDeTemas`
(JSON plano protegido por `threading.Lock`), todos gitignored (runtime) sob
`tipos/<id>/feedback/`:

  metricas.json    métricas + curva de retenção por vídeo publicado (dict por video_id),
                   com os marcos de maturação já coletados (para não re-puxar)
  findings.json    o último rollup por dimensão (recomputado quando os inputs mudam)
  propostas.json   ajustes propostos aguardando aprovação humana (gate advisory)
  aplicados.json   histórico do que foi aplicado (numérico/guia), com o valor anterior
                   para reversão

Este módulo só guarda/lê — não coleta, não agrega, não aplica. As formas exatas dos
registros são dos módulos que os produzem (ingestao/agregacao/roteador/aplicacao);
aqui os stores são propositalmente genéricos.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Store:
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
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(self._vazio))

    def _salvar(self, dados) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class MetricasStore(_Store):
    """Métricas + curva de retenção por vídeo (dict keyed por video_id)."""

    def __init__(self, caminho: Path):
        super().__init__(caminho, {})

    def ler(self) -> dict:
        with self._lock:
            return self._carregar()

    def video(self, video_id: str) -> dict | None:
        return self.ler().get(video_id)

    def gravar_video(self, video_id: str, dados: dict) -> None:
        with self._lock:
            todos = self._carregar()
            todos[video_id] = {**dados, "atualizado_em": _agora()}
            self._salvar(todos)

    def videos(self) -> list[dict]:
        """Todos os registros de vídeo (com o video_id embutido em `id`)."""
        return [{"id": vid, **dados} for vid, dados in self.ler().items()]


class FindingsStore(_Store):
    """O último rollup por dimensão (recomputado quando os inputs mudam)."""

    def __init__(self, caminho: Path):
        super().__init__(caminho, {"calculado_em": None, "assinatura": None, "itens": []})

    def ler(self) -> dict:
        with self._lock:
            return self._carregar()

    def itens(self) -> list[dict]:
        return self.ler().get("itens", [])

    def assinatura(self) -> str | None:
        """Hash dos inputs do último cálculo — permite pular recomputo idêntico."""
        return self.ler().get("assinatura")

    def substituir(self, itens: list[dict], assinatura: str | None = None) -> dict:
        with self._lock:
            dados = {"calculado_em": _agora(), "assinatura": assinatura, "itens": list(itens)}
            self._salvar(dados)
            return dados


class PropostasStore(_Store):
    """Ajustes propostos aguardando aprovação humana (gate advisory)."""

    def __init__(self, caminho: Path):
        super().__init__(caminho, [])

    def listar(self) -> list[dict]:
        with self._lock:
            return self._carregar()

    def pendentes(self) -> list[dict]:
        return [p for p in self.listar() if p.get("status", "pendente") == "pendente"]

    def adicionar(self, proposta: dict) -> dict:
        """Insere uma proposta, atribuindo id/criado_em/status quando ausentes."""
        registro = {"criado_em": _agora(), "status": "pendente", **proposta}
        registro["id"] = proposta.get("id") or uuid.uuid4().hex[:8]
        with self._lock:
            dados = self._carregar()
            dados.insert(0, registro)
            self._salvar(dados)
        return registro

    def obter(self, proposta_id: str) -> dict | None:
        for p in self.listar():
            if p.get("id") == proposta_id:
                return p
        return None

    def definir_status(self, proposta_id: str, status: str) -> dict | None:
        with self._lock:
            dados = self._carregar()
            alvo = None
            for p in dados:
                if p.get("id") == proposta_id:
                    p["status"] = status
                    p["resolvido_em"] = _agora()
                    alvo = p
                    break
            if alvo is not None:
                self._salvar(dados)
            return alvo

    def remover(self, proposta_id: str) -> bool:
        with self._lock:
            dados = self._carregar()
            restantes = [p for p in dados if p.get("id") != proposta_id]
            if len(restantes) == len(dados):
                return False
            self._salvar(restantes)
            return True

    def existe_equivalente(self, chave: str) -> bool:
        """Já há uma proposta pendente com essa chave de idempotência?"""
        return any(
            p.get("chave") == chave for p in self.pendentes()
        ) if chave else False


class AplicadosStore(_Store):
    """Histórico do que foi aplicado, com o valor anterior (para reverter)."""

    def __init__(self, caminho: Path):
        super().__init__(caminho, [])

    def registrar(self, registro: dict) -> dict:
        registro = {"aplicado_em": _agora(), **registro}
        with self._lock:
            dados = self._carregar()
            dados.insert(0, registro)
            self._salvar(dados)
        return registro

    def listar(self) -> list[dict]:
        with self._lock:
            return self._carregar()


def _pasta(tipo) -> Path:
    return tipo.caminho / "feedback"


def metricas_de(tipo) -> MetricasStore:
    return MetricasStore(_pasta(tipo) / "metricas.json")


def findings_de(tipo) -> FindingsStore:
    return FindingsStore(_pasta(tipo) / "findings.json")


def propostas_de(tipo) -> PropostasStore:
    return PropostasStore(_pasta(tipo) / "propostas.json")


def aplicados_de(tipo) -> AplicadosStore:
    return AplicadosStore(_pasta(tipo) / "aplicados.json")
