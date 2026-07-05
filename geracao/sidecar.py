"""Sidecar da Geração — o registro que acompanha o vídeo até a Publicação.

Ao lado do `video_final.mp4`, a Geração grava um `sidecar.json` com tudo que a
Publicação (e o histórico) precisa saber sobre o artefato sem reabrir o vídeo:
tema, roteiro, nº de cenas, duração, e a procedência (provedores/modelos + custo
por etapa). É o handoff explícito entre os pilares — a Publicação lê o sidecar em
vez de depender do layout interno da pasta de saída.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

NOME_ARQUIVO = "sidecar.json"


def montar(tema: str, frases: list, duracao_seg: float, ledger) -> dict:
    """Constrói o dicionário do sidecar a partir do run (função pura)."""
    return {
        "tema": tema,
        "roteiro": "\n".join(str(f[1]) for f in frases),
        "n_cenas": len(frases),
        "duracao_seg": round(float(duracao_seg), 3),
        "custo_total_usd": round(ledger.total(), 6),
        "custos": ledger.itens(),
        "provedores": ledger.provedores(),
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }


def escrever(base: str | Path, dados: dict) -> Path:
    """Grava o sidecar.json na pasta do run e devolve o caminho."""
    caminho = Path(base) / NOME_ARQUIVO
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return caminho


def ler(base: str | Path) -> dict | None:
    """Lê o sidecar.json de uma pasta de run (None se ausente/ilegível)."""
    caminho = Path(base) / NOME_ARQUIVO
    if not caminho.exists():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
