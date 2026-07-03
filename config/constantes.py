FREQUENCIAS = ("daily", "weekly", "monthly")

VISIBILIDADES = ("private", "unlisted", "public")

FONTES_TEMA = ("manual", "trends", "analise")

# Modos de geração das cenas do vídeo: "ia" gera cada imagem por IA (Together);
# "personagem" usa foto do Pexels de fundo + PNG do personagem por cima.
MODOS_IMAGEM = ("ia", "personagem")

# Feeds disponíveis no Trends MCP (fonte de temas por tendência). Lista oficial
# da API; "Google Trends" é o padrão para "tema em alta do dia".
FEEDS_TRENDS = (
    "Google Trends",
    "YouTube Trending",
    "TikTok Trending Hashtags",
    "Reddit Hot Posts",
    "Wikipedia Trending",
    "X (Twitter) Trending",
    "Google News Top News",
    "Reddit World News",
)
