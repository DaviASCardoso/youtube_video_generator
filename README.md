# 🎬 Gerador Automático de Vídeos para YouTube

> **Status:** Em desenvolvimento ativo

## Visão Geral

Pipeline 100% automatizado para geração e publicação periódica de vídeos longos no YouTube. Cada etapa é delegada a um modelo de IA especializado — do roteiro à publicação — sem intervenção humana.

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

## Roadmap

**Em desenvolvimento**
- [x] Geração do roteiro em linguagem natural
- [x] Separação do roteiro em períodos narráveis
- [x] Geração dos prompts de imagem
- [x] Geração das imagens com referência de estilo
- [x] Geração da narração
- [x] Edição e montagem do vídeo
- [ ] Publicação automática

**Futuro**
- [ ] Interface web para controle e monitoramento
- [ ] Análise de desempenho dos vídeos publicados para refinamento automático do pipeline
- [ ] Detecção de tendências para adaptação dinâmica dos temas