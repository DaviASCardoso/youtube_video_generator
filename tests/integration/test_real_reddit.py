"""Chamada real aos feeds .rss do Reddit (sem chave). Rode com: pytest --real-api"""

import pytest

from descoberta.fontes import reddit

pytestmark = pytest.mark.real_api


def test_reddit_retorna_candidatos():
    out = reddit.buscar(None, {"subreddits": ["brasil"], "limite": 5, "periodo": "day"})
    assert isinstance(out, list)
    assert len(out) > 0
    assert all(c.texto and c.fonte == "reddit" for c in out)
