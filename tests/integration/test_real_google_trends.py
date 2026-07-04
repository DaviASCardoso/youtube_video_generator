"""Chamada real ao Google Trends (fork pytrends-modern). Rode com: pytest --real-api

Fonte não-oficial e frágil (pode ser bloqueada/rate-limited): a asserção é
propositalmente leve — confirma que a integração roda e devolve uma lista.
"""

import pytest

from descoberta.fontes import google_trends

pytestmark = pytest.mark.real_api


def test_google_trends_retorna_lista():
    out = google_trends.buscar(None, {"geo": "BR", "limite": 5})
    assert isinstance(out, list)
    assert all(c.fonte == "google_trends" for c in out)
