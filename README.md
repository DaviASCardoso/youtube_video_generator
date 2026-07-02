# 🎬 Gerador Automático de Vídeos para YouTube

> **Status:** Em desenvolvimento ativo

## Visão Geral

Pipeline 100% automatizado para geração e publicação periódica de vídeos longos no YouTube. Cada etapa é delegada a um modelo de IA especializado — do roteiro à publicação — sem intervenção humana.

O sistema suporta múltiplos **tipos de vídeo** rodando lado a lado (ex: canais ou personas diferentes), cada um com seu próprio agendamento, prompts, voz, configurações de geração e fila de temas. Cada tipo vive em sua própria pasta dentro de `tipos/`.

Um **painel web** (`uvicorn api.app:app`) permite controlar tudo isso sem editar arquivos JSON ou rodar scripts manualmente: criar/editar/duplicar/renomear/excluir tipos, editar prompts e configurações com validação, gerenciar a fila de temas, disparar execuções manuais e acompanhar logs ao vivo e o histórico de execuções.

## Pipeline

```
Roteiro  →  Prompts de Imagem  →  Imagens  →  Narração  →  Edição  →  Publicação
 Groq           Groq             Together     Google TTS   (local)    YouTube API
```

Cada etapa é isolada e independente, seguindo o princípio de que modelos de IA performam melhor quando fazem uma coisa de cada vez.

## Tecnologias

| Etapa | Tecnologia |
|---|---|
| Linguagem principal | Python |
| Geração de roteiro e prompts | Groq API (Llama 3.3 70B) |
| Geração de imagens | Together API (FLUX.2 Dev) |
| Narração | Google Cloud TTS |
| Publicação | YouTube Data API v3 |
| Painel web | FastAPI + Jinja2 + HTMX |
| Agendamento | APScheduler |

## Como rodar

```
pip install -r requirements.txt
uvicorn api.app:app
```

Isso sobe o painel web em `http://127.0.0.1:8000` e, no mesmo processo, o agendador que gera vídeos automaticamente para cada tipo ativo em `tipos/`.

## Roadmap

**Em desenvolvimento**
- [x] Geração do roteiro em linguagem natural
- [x] Separação do roteiro em períodos narráveis
- [x] Geração dos prompts de imagem
- [x] Geração das imagens com referência de estilo
- [x] Geração da narração
- [x] Edição e montagem do vídeo
- [x] Suporte a múltiplos tipos de vídeo (agendamento, prompts, voz e fila de temas independentes por tipo)
- [x] Interface web para controle e monitoramento
- [ ] Publicação automática

**Futuro**
- [ ] Análise de desempenho dos vídeos publicados para refinamento automático do pipeline
- [ ] Detecção de tendências para adaptação dinâmica dos temas