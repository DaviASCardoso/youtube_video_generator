"""Chamada real ao YouTube (não-destrutiva). Rode com: pytest --real-api

NÃO sobe vídeo: só confirma que a cadeia OAuth funciona e mostra qual canal foi
autenticado (channels.list mine=true). Pula se ainda não houver token — rode
antes: python -m scripts.youtube auth --tipo cetico_pratico
"""

import pytest

from config.tipos import carregar_tipo
from scripts import youtube

pytestmark = pytest.mark.real_api


def test_youtube_autenticado_sem_subir_video():
    tipo = carregar_tipo("cetico_pratico")
    if not youtube._caminho_token(tipo).exists():
        pytest.skip(
            "sem youtube_token.json — rode: "
            "python -m scripts.youtube auth --tipo cetico_pratico"
        )
    canal = youtube.canal_autenticado(tipo)
    assert canal["id"]
    assert canal["titulo"]
