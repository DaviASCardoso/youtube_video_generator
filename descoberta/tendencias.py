"""Armazenamento de sinais já consumidos por tipo (dedupe) + prompt de critério.

`HistoricoTendencias` guarda cada sinal (tendência crua) que a Descoberta já
consumiu por tipo — a fonte de verdade do dedupe, já que o pool de ideias não
guarda a tendência crua e o histórico de execuções guarda o tema gerado (não a
tendência). Consumido por `descoberta.dedup`.

`_prompt_do_tipo` / `_default_prompt_tendencia` resolvem o prompt de critério/
persona do tipo (system_prompt_tendencia.txt), usado pela avaliação de fit.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent
_HISTORICO_PATH = BASE.parent / "tendencias" / "historico.json"


def _normalizar(nome: str) -> str:
    """Forma canônica para comparar tendências no dedupe (minúsculas, espaços colapsados)."""
    return " ".join(nome.lower().split())


class HistoricoTendencias:
    """Registro das tendências já usadas por tipo, para o dedupe das últimas semanas.

    Mesmo padrão de FilaDeTemas/HistoricoExecucoes: lista plana em JSON, protegida
    por um threading.Lock (o job das 06:00 e um eventual disparo manual podem
    escrever ao mesmo tempo).
    """

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)
        self._lock = threading.Lock()

    def _carregar(self) -> list[dict]:
        if not self._caminho.exists():
            return []
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{self._caminho.name} inválido: {e}") from e
        if not isinstance(dados, list):
            raise ValueError(f"{self._caminho.name} deve ser uma lista.")
        return dados

    def _salvar(self, registros: list[dict]) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def registrar(self, tipo_id: str, tendencia: str, feed: str, tema_gerado: str) -> dict:
        registro = {
            "tipo_id": tipo_id,
            "tendencia": tendencia,
            "feed": feed,
            "tema_gerado": tema_gerado,
            "escolhido_em": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            registros = self._carregar()
            registros.insert(0, registro)
            self._salvar(registros)
        return registro

    def trends_recentes(self, tipo_id: str, dias: int) -> set[str]:
        """Nomes de tendências (normalizados) usados por um tipo nos últimos `dias`."""
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        recentes = set()
        for r in self._carregar():
            if r.get("tipo_id") != tipo_id:
                continue
            try:
                quando = datetime.fromisoformat(r["escolhido_em"])
            except (KeyError, ValueError):
                continue
            if quando >= limite:
                recentes.add(_normalizar(r.get("tendencia", "")))
        return recentes

    def listar(self) -> list[dict]:
        return self._carregar()


historico_tendencias = HistoricoTendencias(_HISTORICO_PATH)


def _default_prompt_tendencia() -> str:
    """Instrução usada quando um tipo ainda não tem system_prompt_tendencia.txt."""
    return (
        "Você recebe um tema em alta na internet e o transforma em um tema de "
        "vídeo curto para um canal de desenvolvimento pessoal cético, irônico e "
        "direto. Responda em português do Brasil. Devolva um 'tema' pronto para "
        "virar roteiro e uma 'justificativa' curta explicando a conexão com o "
        "canal. Se a tendência não tiver relação com desenvolvimento pessoal, "
        "encontre um ângulo honesto e interessante mesmo assim."
    )


def _prompt_do_tipo(tipo) -> str:
    caminho = tipo.assets_dir / "system_prompt_tendencia.txt"
    if caminho.exists():
        conteudo = caminho.read_text(encoding="utf-8").strip()
        if conteudo:
            return conteudo
    return _default_prompt_tendencia()
