"""Chamada real ao Wikimedia Pageviews (sem chave). Rode com: pytest --real-api"""

import pytest

from descoberta.fontes import wikipedia

pytestmark = pytest.mark.real_api


def test_wikipedia_retorna_candidatos():
    out = wikipedia.buscar(None, {"limite": 5})
    assert isinstance(out, list)
    assert len(out) > 0
    assert all(c.texto and c.fonte == "wikipedia" for c in out)
