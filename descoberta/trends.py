"""Cliente mínimo do Trends MCP para buscar os temas em alta do dia.

Usa a API REST (mais simples que o transporte MCP para um job de cron): um POST
com a chave no header. Precisa de TRENDS_MCP_API_KEY no .env (chave gratuita em
https://www.trendsmcp.ai). Usa apenas a biblioteca padrão (urllib) — sem
dependências novas, no mesmo estilo de scripts/pexels.py.

Observação: o Trends MCP não filtra por região — o feed "Google Trends" é
global (mais voltado aos EUA). A etapa seguinte (Gemini, com o contexto pt-BR do
canal) reescreve a tendência para o público do canal, o que ameniza isso.
"""

import json
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

TRENDS_URL = "https://api.trendsmcp.ai/api"

# Sem um User-Agent "de navegador", APIs atrás de proteção anti-bot costumam
# responder 403 (foi o que aconteceu com o Pexels) — barato prevenir.
USER_AGENT = "Mozilla/5.0 (compatible; GeradorDeVideos/1.0)"


def tem_chave() -> bool:
    return bool(os.getenv("TRENDS_MCP_API_KEY"))


def buscar_tendencias(feed: str = "Google Trends", limite: int = 25, timeout: int = 60) -> list[str]:
    """Busca os temas em alta de um feed, em ordem de ranking.

    Args:
        feed: Nome do feed (ex.: "Google Trends"). Ver FEEDS_TRENDS em config/constantes.py.
        limite: Quantos itens trazer (1–200).
        timeout: Timeout de rede, em segundos.

    Returns:
        Lista de nomes (strings) em ordem do ranking (1º, 2º, ...). Lista vazia se
        não houver chave ou se a requisição falhar — quem chama registra e pula o dia.
    """
    chave = os.getenv("TRENDS_MCP_API_KEY")
    if not chave:
        print("    [trends] TRENDS_MCP_API_KEY não configurada.")
        return []

    corpo = json.dumps({"mode": "top_trends", "type": feed, "limit": limite}).encode("utf-8")
    req = urllib.request.Request(
        TRENDS_URL,
        data=corpo,
        headers={
            "Authorization": f"Bearer {chave}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read())
    except Exception as e:
        print(f"    [trends] falha ao buscar '{feed}': {e}")
        return []

    # A API embrulha a resposta em {"statusCode": ..., "body": "<json string>"} —
    # o payload de verdade (com "data") vem como string dentro de "body".
    if isinstance(dados, dict) and "body" in dados:
        corpo_resp = dados["body"]
        if isinstance(corpo_resp, str):
            try:
                dados = json.loads(corpo_resp)
            except json.JSONDecodeError as e:
                print(f"    [trends] body inválido para '{feed}': {e}")
                return []
        elif isinstance(corpo_resp, dict):
            dados = corpo_resp

    # data é uma lista de pares [rank, nome], já em ordem de ranking.
    itens = dados.get("data", [])
    nomes = []
    for item in itens:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            nomes.append(str(item[1]).strip())
        elif isinstance(item, str):
            nomes.append(item.strip())
    return [n for n in nomes if n]


if __name__ == "__main__":
    if not tem_chave():
        print("TRENDS_MCP_API_KEY não configurada no .env")
    else:
        nomes = buscar_tendencias()
        print(f"{len(nomes)} tendências:")
        for i, nome in enumerate(nomes, start=1):
            print(f"  {i:2d}. {nome}")
