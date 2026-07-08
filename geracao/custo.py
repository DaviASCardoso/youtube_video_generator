"""Custo por etapa e orçamento por vídeo/dia.

Geração é onde o dinheiro é gasto. Cada estágio reporta seu custo estimado a um
`Ledger` do run; o `GastoDiario` acumula o gasto do dia (entre runs). Antes de
uma etapa cara, o pipeline chama `checar_orcamento` — se um run estouraria o teto
(por vídeo ou por dia), ele degrada (provedor mais barato / menos imagens) ou
para, em vez de furar o orçamento.

As tabelas abaixo são **estimativas** em USD (o ajuste fino é feito pelos tetos
configuráveis no painel, não por precisão perfeita destas constantes).
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import caminhos

BASE = Path(__file__).parent
_CUSTO_DIARIO_PATH = caminhos.raiz("execucoes") / "custo_diario.json"  # dentro de execucoes/ (gitignored)

# Estimativas de custo (USD).
CUSTO_GROQ_CHAMADA = 0.0005     # uma chamada de roteiro/plano (Groq llama-3.3-70b)
CUSTO_FLUX_IMAGEM = 0.02        # uma imagem FLUX.2-dev (Together)
CUSTO_TTS_POR_CHAR = 0.000016   # Google TTS Neural2/Chirp, por caractere
CUSTO_PEXELS = 0.0              # banco de imagens gratuito
CUSTO_PLACEHOLDER = 0.0         # gradiente local


def custo_tts(texto: str) -> float:
    """Custo estimado de sintetizar um texto (por caractere)."""
    return len(texto) * CUSTO_TTS_POR_CHAR


class Ledger:
    """Acumula o custo por etapa de um único run (em memória)."""

    def __init__(self):
        self._itens: list[dict] = []

    def registrar(self, estagio: str, provedor: str, custo: float, **extra) -> None:
        self._itens.append(
            {"estagio": estagio, "provedor": provedor, "custo": float(custo), **extra}
        )

    def total(self) -> float:
        return sum(i["custo"] for i in self._itens)

    def itens(self) -> list[dict]:
        return list(self._itens)

    def por_estagio(self) -> dict:
        agregado: dict[str, float] = {}
        for i in self._itens:
            agregado[i["estagio"]] = agregado.get(i["estagio"], 0.0) + i["custo"]
        return agregado

    def provedores(self) -> dict:
        return {i["estagio"]: i["provedor"] for i in self._itens}


class GastoDiario:
    """Gasto acumulado por dia (UTC), persistido entre runs. Mesmo padrão de
    flat-JSON + threading.Lock dos demais stores do projeto."""

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

    def registrar(self, usd: float) -> None:
        with self._lock:
            dados = self._carregar()
            dia = self._hoje()
            dados[dia] = round(dados.get(dia, 0.0) + float(usd), 6)
            self._salvar(dados)

    def gasto_hoje(self) -> float:
        return float(self._carregar().get(self._hoje(), 0.0))


gasto_diario = GastoDiario(_CUSTO_DIARIO_PATH)


def checar_orcamento(
    gasto_video: float, custo_previsto: float, gasto_hoje: float, cfg_orcamento: dict
) -> str:
    """Decide se pode pagar a próxima etapa.

    Um teto igual a 0 significa **sem limite** (só medir). Retorna "ok" quando cabe;
    caso contrário retorna a ação configurada ("degradar" ou "parar").
    """
    por_video = cfg_orcamento["por_video_usd"]
    por_dia = cfg_orcamento["por_dia_usd"]

    estoura_video = por_video > 0 and (gasto_video + custo_previsto) > por_video
    estoura_dia = por_dia > 0 and (gasto_hoje + custo_previsto) > por_dia

    if estoura_video or estoura_dia:
        return cfg_orcamento["acao"]
    return "ok"
