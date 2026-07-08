"""Trilha de auditoria da Conformidade — por tipo, append-only.

Para cada julgamento: quais checagens rodaram, o que passou, o que foi vetado ou
sinalizado e por quê, e qual disclosure foi decidido e com que base. Se a plataforma um
dia questionar o canal, a história existe. Registrar é papel da Conformidade; exibir é do
Controle.

Guarda um `auditoria.json` por tipo em `tipos/<id>/conformidade/auditoria.json` (JSON +
lock, mais recentes primeiro). Cobre tanto o **veto de tema** na Descoberta (que acontece
antes de existir pasta de run) quanto as **checagens de publicação** — por isso é um store
por tipo, não um arquivo por run.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# Limita o crescimento do arquivo (mantém os N registros mais recentes).
_MAX_REGISTROS = 500


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


class Auditoria:
    """Trilha de auditoria de um tipo (JSON append-only protegido por lock)."""

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)
        self._lock = threading.Lock()

    def _carregar(self) -> list[dict]:
        if not self._caminho.exists():
            return []
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return dados if isinstance(dados, list) else []

    def _salvar(self, registros: list[dict]) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def registrar(self, registro: dict) -> dict:
        """Anexa um registro de auditoria (carimba `quando` se ausente). Mais recentes
        primeiro; o arquivo é aparado em `_MAX_REGISTROS`."""
        registro = dict(registro)
        registro.setdefault("quando", _agora())
        with self._lock:
            registros = self._carregar()
            registros.insert(0, registro)
            self._salvar(registros[:_MAX_REGISTROS])
            return registro

    def listar(self, limite: int | None = None) -> list[dict]:
        """Registros, mais recentes primeiro (opcionalmente os `limite` primeiros)."""
        registros = self._carregar()
        return registros[:limite] if limite is not None else registros

    def de_execucao(self, execucao_id: str) -> list[dict]:
        """Registros ligados a uma execução (por `execucao_id`)."""
        return [r for r in self._carregar() if r.get("execucao_id") == execucao_id]


def _dir_conformidade(tipo) -> Path:
    return Path(tipo.caminho) / "conformidade"


def auditoria_de(tipo) -> Auditoria:
    """A trilha de auditoria de um tipo."""
    return Auditoria(_dir_conformidade(tipo) / "auditoria.json")
