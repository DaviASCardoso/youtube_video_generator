"""Circuit breaker por provedor, persistido em disco.

Se um provedor falha repetidamente, o motor **abre o circuito** — para de mandar
requisições por um cooldown, para não queimar cota e tempo martelando um serviço
morto — e depois manda um único probe **meio-aberto** para testar a recuperação antes
de fechar de novo. Também guarda a janela de falhas recentes, para o motor ser
**adaptativo**: um provedor que falhou o dia todo recebe tratamento mais conservador
(menos retries, failover mais rápido) que um confiável num soluço isolado.

Persistido (sobrevive a restart) em `execucoes/circuitos.json`, mesmo padrão flat-JSON
+ `threading.Lock` de `geracao.custo.GastoDiario` / `publicacao.quota.QuotaDiaria`.

Estados: `fechado` (normal), `aberto` (em cooldown, pula direto para failover),
`meio_aberto` (cooldown passou; um probe é permitido). São **derivados** de
`consecutivas`/`ultima_falha` + a política — o store guarda fatos, não o estado.
"""

import json
import threading
import time
from pathlib import Path

BASE = Path(__file__).parent
_CIRCUITOS_PATH = BASE.parent / "execucoes" / "circuitos.json"

FECHADO = "fechado"
ABERTO = "aberto"
MEIO_ABERTO = "meio_aberto"

# Máximo de timestamps de falha guardados por provedor (limita o crescimento do arquivo).
_MAX_FALHAS = 100


class RegistroCircuitos:
    """Estado de circuito por provedor (fatos crus; o estado é derivado)."""

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)
        self._lock = threading.Lock()

    def _carregar(self) -> dict:
        if not self._caminho.exists():
            return {}
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return dados if isinstance(dados, dict) else {}

    def _salvar(self, dados: dict) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _get(self, provedor: str) -> dict:
        return self._carregar().get(provedor, {"falhas": [], "consecutivas": 0, "ultima_falha": None})

    def registrar_falha(self, provedor: str, agora: float | None = None) -> None:
        agora = time.time() if agora is None else agora
        with self._lock:
            dados = self._carregar()
            p = dados.setdefault(provedor, {"falhas": [], "consecutivas": 0, "ultima_falha": None})
            p["falhas"] = (p.get("falhas", []) + [agora])[-_MAX_FALHAS:]
            p["consecutivas"] = int(p.get("consecutivas", 0)) + 1
            p["ultima_falha"] = agora
            self._salvar(dados)

    def registrar_sucesso(self, provedor: str) -> None:
        """Fecha o circuito: zera as falhas consecutivas (mantém o histórico da janela)."""
        with self._lock:
            dados = self._carregar()
            if provedor in dados:
                dados[provedor]["consecutivas"] = 0
                self._salvar(dados)

    def estado(self, provedor: str, politica, agora: float | None = None) -> str:
        """Estado atual do circuito do provedor, derivado dos fatos + política."""
        agora = time.time() if agora is None else agora
        p = self._get(provedor)
        limiar = int(politica.circuito["limiar_falhas"])
        cooldown = float(politica.circuito["cooldown_seg"])
        if int(p.get("consecutivas", 0)) < limiar:
            return FECHADO
        ultima = p.get("ultima_falha") or 0
        if agora >= ultima + cooldown:
            return MEIO_ABERTO  # cooldown passou: um probe é permitido
        return ABERTO

    def falhas_recentes(self, provedor: str, janela_seg: float, agora: float | None = None) -> int:
        """Nº de falhas dentro da janela (para o tratamento adaptativo)."""
        agora = time.time() if agora is None else agora
        corte = agora - float(janela_seg)
        return sum(1 for t in self._get(provedor).get("falhas", []) if t >= corte)

    def limpar(self, provedor: str | None = None) -> None:
        """Reseta um provedor (ou todos) — para testes/reset manual."""
        with self._lock:
            if provedor is None:
                self._salvar({})
                return
            dados = self._carregar()
            if provedor in dados:
                del dados[provedor]
                self._salvar(dados)


circuitos = RegistroCircuitos(_CIRCUITOS_PATH)
