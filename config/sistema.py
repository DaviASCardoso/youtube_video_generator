from pathlib import Path

from config.settings import Config

_CAMINHO = Path(__file__).parent / "sistema.json"

sistema = Config(_CAMINHO)

# Estrutura/defaults do sistema.json, para o formulário schema-driven do Controle.
SISTEMA_PADRAO = {
    "execucao": {"max_simultaneo": 1},
    "saida": {"pasta_base": "output"},
    "video": {"fps": 24, "codec": "libx264", "audio_codec": "aac"},
}

UI_HINTS = {
    "execucao": {"rotulo": "Execução"},
    "execucao.max_simultaneo": {"rotulo": "Vídeos simultâneos (máximo)", "min": 1, "passo": "1"},
    "saida": {"rotulo": "Saída"},
    "saida.pasta_base": {"rotulo": "Pasta base de saída"},
    "video": {"rotulo": "Vídeo"},
    "video.fps": {"rotulo": "FPS", "min": 1, "max": 120, "passo": "1"},
    "video.codec": {"rotulo": "Codec de vídeo"},
    "video.audio_codec": {"rotulo": "Codec de áudio"},
}
