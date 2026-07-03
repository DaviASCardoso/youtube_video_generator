"""Chamada real ao Trends MCP (tendências do dia). Rode com: pytest --real-api"""

import pytest

from scripts import trends

pytestmark = pytest.mark.real_api


def test_trends_retorna_nomes(exigir_chave):
    exigir_chave("TRENDS_MCP_API_KEY")
    nomes = trends.buscar_tendencias(limite=5)
    assert isinstance(nomes, list)
    assert len(nomes) > 0
    assert all(isinstance(n, str) and n for n in nomes)
