"""Coleta diária de temas por tendência (Trends MCP + Gemini).

Fluxo do job das 06:00 (`coletar_temas_do_dia`):
  1. Uma única busca de tendências (compartilhada entre todos os tipos).
  2. Para cada tipo ativo: escolhe a 1ª tendência que NÃO foi usada por aquele
     tipo nas últimas N semanas (dedupe), chama o Gemini com o contexto do tipo
     para virar um tema, coloca na fila (fonte="trends") e registra a tendência
     usada no histórico (para o dedupe dos próximos dias).

`HistoricoTendencias` é o armazenamento das tendências já usadas por tipo — a
fila de temas não guarda a tendência crua, e o histórico de execuções guarda o
tema gerado (não a tendência), então o dedupe precisa do próprio registro.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.sistema import sistema
from config.tipos import listar_tipos_ativos
from descoberta import gemini, trends

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


def _escolher_tendencia(nomes: list[str], recentes: set[str]) -> str | None:
    """Primeira tendência (em ordem de ranking) ainda não usada recentemente."""
    for nome in nomes:
        if _normalizar(nome) not in recentes:
            return nome
    return None


def coletar_temas_do_dia(dry_run: bool = False) -> dict:
    """Executa um ciclo de coleta: uma busca de tendências + um tema por tipo ativo.

    Args:
        dry_run: Se True, não adiciona à fila nem registra no histórico — só
            calcula e imprime o que faria (para testes).

    Returns:
        Resumo do ciclo (por tipo: tendência escolhida e tema gerado, ou o motivo
        de ter pulado).
    """
    if not sistema.get("tendencias.ativo"):
        print("[tendências] desativado nas configurações, nada a fazer.")
        return {"ativo": False, "tipos": []}

    feed = sistema.get("tendencias.feed")
    limite = sistema.get("tendencias.limite")
    prioridade = sistema.get("tendencias.prioridade")
    dias = sistema.get("tendencias.dias_historico")

    print(f"[tendências] buscando '{feed}' (limite {limite})...")
    nomes = trends.buscar_tendencias(feed=feed, limite=limite)
    if not nomes:
        print("[tendências] nenhuma tendência retornada — pulando o dia.")
        return {"ativo": True, "feed": feed, "erro": "sem tendências", "tipos": []}

    resumo = {"ativo": True, "feed": feed, "tipos": []}

    for tipo in listar_tipos_ativos():
        recentes = historico_tendencias.trends_recentes(tipo.id, dias)
        escolhido = _escolher_tendencia(nomes, recentes)

        if escolhido is None:
            print(f"  [{tipo.nome}] todas as {len(nomes)} tendências já foram usadas em {dias} dias — pulando.")
            resumo["tipos"].append({"tipo_id": tipo.id, "status": "todas_repetidas"})
            continue

        try:
            gerado = gemini.gerar_tema_de_tendencia(escolhido, _prompt_do_tipo(tipo))
        except Exception as e:
            print(f"  [{tipo.nome}] falha no Gemini para '{escolhido}': {e}")
            resumo["tipos"].append({"tipo_id": tipo.id, "status": "erro_gemini", "erro": str(e)})
            continue

        if dry_run:
            print(f"  [{tipo.nome}] (dry-run) tendência='{escolhido}' -> tema='{gerado.tema}'")
        else:
            tipo.temas.adicionar(gerado.tema, prioridade, fonte="trends")
            historico_tendencias.registrar(tipo.id, escolhido, feed, gerado.tema)
            print(f"  [{tipo.nome}] tendência='{escolhido}' -> tema='{gerado.tema}' (adicionado à fila)")

        resumo["tipos"].append(
            {
                "tipo_id": tipo.id,
                "status": "ok",
                "tendencia": escolhido,
                "tema": gerado.tema,
            }
        )

    return resumo


if __name__ == "__main__":
    import sys

    seco = "--commit" not in sys.argv  # por padrão roda em dry-run (não mexe na fila)
    if seco:
        print("Rodando em DRY-RUN (não adiciona à fila). Use --commit para valer.\n")
    coletar_temas_do_dia(dry_run=seco)
