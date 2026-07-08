"""Cota diária de upload por credencial.

Upload é caro em **cota**, não em dólar: no YouTube um `videos.insert` consome ~1600
das 10000 unidades diárias, então só cabem poucos por dia por credencial. Esta store
conta os uploads feitos por credencial a cada dia (UTC) e a Publicação consulta
`checar_cap` antes de subir — se o cap foi atingido, a ação é **adiar** para o dia
seguinte, nunca esgotar a cota.

Mesmo padrão flat-JSON + `threading.Lock` de `geracao.custo.GastoDiario`; o arquivo
fica em `execucoes/` (já gitignored). A "credencial" é uma string estável escolhida
por quem chama — para o YouTube, `youtube:<tipo_id>` (um projeto Cloud por canal).
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import caminhos

BASE = Path(__file__).parent
_QUOTA_PATH = caminhos.raiz("execucoes") / "quota_publicacao.json"


class QuotaDiaria:
    """Contagem de uploads por credencial e por dia (UTC), persistida entre runs."""

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)
        self._lock = threading.Lock()

    def _carregar(self) -> dict:
        if not self._caminho.exists():
            return {}
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return dados if isinstance(dados, dict) else {}

    def _salvar(self, dados: dict) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _hoje(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _chave(self, credencial: str) -> str:
        return f"{credencial}:{self._hoje()}"

    def registrar(self, credencial: str, quantidade: int = 1) -> None:
        """Contabiliza `quantidade` uploads feitos por essa credencial hoje."""
        with self._lock:
            dados = self._carregar()
            chave = self._chave(credencial)
            dados[chave] = int(dados.get(chave, 0)) + int(quantidade)
            self._salvar(dados)

    def uploads_hoje(self, credencial: str) -> int:
        return int(self._carregar().get(self._chave(credencial), 0))


quota_diaria = QuotaDiaria(_QUOTA_PATH)


def checar_cap(uploads_hoje: int, cap_diario: int) -> bool:
    """Diz se ainda há espaço para mais um upload hoje.

    `cap_diario == 0` significa **sem limite** (só medir). Retorna True quando cabe
    um upload; False quando o cap já foi atingido (quem chama adia para o dia seguinte).
    """
    if cap_diario <= 0:
        return True
    return uploads_hoje < cap_diario
