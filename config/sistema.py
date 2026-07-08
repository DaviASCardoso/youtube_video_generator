from pathlib import Path

from config.settings import Config

_CAMINHO = Path(__file__).parent / "sistema.json"

sistema = Config(_CAMINHO)

# Estrutura/defaults do sistema.json, para o formulário schema-driven do Controle.
# `saida.pasta_base` continua sendo a raiz de saída/render; o bloco `caminhos`
# expõe as demais raízes de armazenamento (histórico+logs, dedupe, conteúdo por
# tipo) para que possam apontar para um mount (NAS) sem editar código. Os padrões
# são exatamente os locais de hoje — nada se move até o ajuste mudar. Toda leitura
# de caminho passa por `config.caminhos`, a fonte única de resolução.
SISTEMA_PADRAO = {
    "execucao": {"max_simultaneo": 1},
    "saida": {"pasta_base": "output"},
    "caminhos": {
        "execucoes": "execucoes",
        "tendencias": "tendencias",
        "tipos": "tipos",
    },
    "video": {"fps": 24, "codec": "libx264", "audio_codec": "aac"},
}

UI_HINTS = {
    "execucao": {"rotulo": "Execução"},
    "execucao.max_simultaneo": {"rotulo": "Vídeos simultâneos (máximo)", "min": 1, "passo": "1"},
    "saida": {"rotulo": "Saída"},
    "saida.pasta_base": {
        "rotulo": "Pasta base de saída (render)",
        "ajuda": "Raiz onde os vídeos/render são gravados. Absoluto ou relativo à raiz do projeto; pode apontar para um mount (NAS).",
    },
    "caminhos": {"rotulo": "Caminhos de armazenamento"},
    "caminhos.execucoes": {
        "rotulo": "Pasta de execuções (histórico + logs)",
        "ajuda": "Raiz do histórico de runs, logs, custo/cota/circuitos. Absoluto ou relativo à raiz do projeto.",
    },
    "caminhos.tendencias": {
        "rotulo": "Pasta de tendências (dedupe)",
        "ajuda": "Raiz do store de sinais já consumidos (dedupe da Descoberta).",
    },
    "caminhos.tipos": {
        "rotulo": "Pasta de tipos (conteúdo por canal)",
        "ajuda": "Raiz do conteúdo por tipo (tipos/<id>/): config, fila, prompts, assets.",
    },
    "video": {"rotulo": "Vídeo"},
    "video.fps": {"rotulo": "FPS", "min": 1, "max": 120, "passo": "1"},
    "video.codec": {"rotulo": "Codec de vídeo"},
    "video.audio_codec": {"rotulo": "Codec de áudio"},
}
