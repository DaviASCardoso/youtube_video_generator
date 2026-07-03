# 🎬 Gerador Automático de Vídeos para YouTube

> **Status:** Em desenvolvimento ativo

## Visão Geral

Pipeline 100% automatizado para geração e publicação periódica de vídeos longos no YouTube. Cada etapa é delegada a um modelo de IA especializado — do roteiro à publicação — sem intervenção humana.

O sistema suporta múltiplos **tipos de vídeo** rodando lado a lado (ex: canais ou personas diferentes), cada um com seu próprio agendamento, prompts, voz, configurações de geração e fila de temas. Cada tipo vive em sua própria pasta dentro de `tipos/`.

Um **painel web** (`uvicorn api.app:app`) permite controlar tudo isso sem editar arquivos JSON ou rodar scripts manualmente: criar/editar/duplicar/renomear/excluir tipos, editar prompts e configurações com validação, gerenciar a fila de temas, disparar execuções manuais e acompanhar logs ao vivo e o histórico de execuções.

## Pipeline

```
Roteiro  →  Cenas  →  Narração  →  Edição  →  Publicação
 Groq       (modo)    Google TTS   (local)    YouTube API
```

Cada etapa é isolada e independente, seguindo o princípio de que modelos de IA performam melhor quando fazem uma coisa de cada vez.

A etapa de cenas tem dois modos, configuráveis por tipo (`imagens.modo`):

- **`ia`** — cada frase vira um prompt de imagem (Groq) e uma imagem gerada por IA (Together / FLUX.2).
- **`personagem`** — para cada frase, a IA decide a **emoção** do personagem e um **termo de busca**; o fundo é uma foto real de banco de imagens (Pexels) e o **PNG do personagem** correspondente à emoção é sobreposto num canto configurável (posição, tamanho e margens editáveis no painel), respeitando a área da interface do YouTube Shorts. Os PNGs do personagem (um por emoção; o `neutro` é obrigatório) são enviados pela aba Prompts do painel. Requer `PEXELS_API_KEY` no `.env` (chave gratuita em pexels.com/api).

## Tecnologias

| Etapa | Tecnologia |
|---|---|
| Linguagem principal | Python |
| Geração de roteiro e prompts | Groq API (Llama 3.3 70B) |
| Geração de imagens (modo ia) | Together API (FLUX.2 Dev) |
| Fundos de cena (modo personagem) | Pexels API |
| Fonte de temas por tendência | Trends MCP + Gemini 3.5 Flash |
| Narração | Google Cloud TTS |
| Publicação | YouTube Data API v3 |
| Painel web | FastAPI + Jinja2 + HTMX |
| Agendamento | APScheduler |

## Fonte de temas por tendência (Trends MCP + Gemini)

Além dos temas manuais, o sistema busca temas automaticamente a partir do que está em alta. Todo dia, no horário configurado (padrão **06:00**), um job global:

1. Busca o tema em alta do dia no **Trends MCP** (uma única busca, compartilhada).
2. Para cada tipo ativo, pula tendências já usadas por aquele tipo nos últimos dias (dedupe configurável), pegando a próxima do ranking.
3. Chama o **Gemini 3.5 Flash** com o contexto do tipo (prompt editável `system_prompt_tendencia.txt`) para transformar a tendência num tema do canal.
4. Adiciona o tema à fila do tipo com `fonte: "trends"`.

Tudo é configurável na página de Configurações (ativar/desativar, horário, fuso, feed, prioridade, quantidade e janela de dedupe). Requer `TRENDS_MCP_API_KEY` e `GEMINI_API_KEY` no `.env`. Observação: o Trends MCP não filtra por região (Google Trends é global); a etapa do Gemini, com o contexto pt-BR do canal, reescreve a tendência para o público.

## Como rodar

```
pip install -r requirements.txt
uvicorn api.app:app
```

Isso sobe o painel web em `http://127.0.0.1:8000` e, no mesmo processo, o agendador que gera vídeos automaticamente para cada tipo ativo em `tipos/`.

### Acessar de outros dispositivos na mesma rede

Por padrão o painel só aceita conexões da própria máquina. Para liberar o acesso de outros aparelhos na mesma rede Wi-Fi/local:

```
uvicorn api.app:app --host 0.0.0.0
```

Depois, descubra o IP local da máquina que está rodando o servidor (`ipconfig` no Windows, procure por "Endereço IPv4" da rede Wi-Fi) e acesse de outro dispositivo por `http://<esse-ip>:8000`. O Windows pode pedir permissão de firewall na primeira vez — permita para redes privadas.

### Login (opcional, recomendado)

Por padrão o painel não exige login. Para fechar o acesso na rede local, defina `ADMIN_USER` e `ADMIN_PASSWORD` no `.env` — com as duas presentes, todo o painel passa a exigir login. Defina também `SESSION_SECRET` (uma string aleatória qualquer) para que a sessão continue válida entre reinícios; sem ela, um segredo novo é gerado a cada inicialização e você é deslogado ao reiniciar.

```
ADMIN_USER=seu_usuario
ADMIN_PASSWORD=sua_senha
SESSION_SECRET=uma_string_longa_e_aleatoria
```

⚠️ O login roda sobre HTTP (sem HTTPS na rede local): ele mantém curiosos e outros dispositivos da rede de fora, mas a senha trafega sem criptografia — não é proteção contra alguém que consiga farejar o tráfego da rede. Sem `ADMIN_USER`/`ADMIN_PASSWORD`, o painel fica aberto: qualquer pessoa na mesma rede pode editar configurações, disparar gerações (que consomem cota das APIs pagas) e excluir tipos de vídeo.

## Publicação no YouTube

O vídeo pronto pode ser publicado automaticamente no YouTube. Cada tipo usa seu **próprio projeto Google Cloud** (um por canal, para isolar a cota de upload — ~6 uploads/dia por projeto), então as credenciais são **por tipo**:

- `tipos/<id>/youtube_client_secret.json` — o OAuth client (Desktop app) baixado do projeto daquele canal. Se ausente, cai no `client_secret_youtube.json` da raiz.
- `tipos/<id>/youtube_token.json` — criado no primeiro consentimento e reusado depois (gitignored).

**Consentimento único** (abre o navegador, você autoriza o canal e o token é salvo):

```
python -m scripts.youtube auth --tipo cetico_pratico
```

Depois disso, ligue **"Publicar automaticamente no YouTube após gerar"** na aba Config do tipo. Recomendação: comece com a visibilidade em **`private`** — o vídeo sobe, mas só você vê, e você promove a público manualmente no YouTube Studio. O título vem do tema e a descrição do roteiro + a "descrição base" do config + `#Shorts` + as tags. A URL publicada aparece no histórico de execuções.

Para publicar um vídeo já gerado na mão:

```
python -m scripts.youtube publicar caminho/para/video_final.mp4 --tipo cetico_pratico
```

⚠️ **Gotcha dos 7 dias:** enquanto o app OAuth estiver em modo **"Testing"** no Google Console, o token expira em 7 dias e a publicação para de funcionar. Ponha o app em **"In production"** (aceitando a tela de "app não verificado" no consentimento único) para tokens duráveis. Se o token expirar, rode o comando `auth` de novo.

## Testes

A pasta `tests/` tem uma suíte de testes unitários (pytest) para toda a lógica fora da camada web — as camadas de configuração (`config/`) e os estágios/fontes do pipeline (`scripts/`). Todas as chamadas de API externas (Groq, Together, Google TTS, Pexels, Trends MCP, Gemini) são mockadas, então a suíte roda offline, rápida e sem gastar cota. Nenhum teste toca nas pastas reais (`tipos/`, `execucoes/`, `tendencias/`) nem no `config/sistema.json`.

```
pip install -r requirements-dev.txt
pytest
```

Convenção: cada nova função fora da parte web ganha um teste correspondente em `tests/`.

### Testes de API real

Além da suíte mockada, `tests/integration/` tem testes que fazem **chamadas reais** a cada API externa (Groq, Together, Google TTS, Pexels, Trends MCP, Gemini) — úteis para checar credenciais e conectividade. Eles ficam de fora do `pytest` normal (gastam cota/dinheiro e precisam de rede + chaves) e só rodam com a flag `--real-api`:

```
pytest --real-api                       # tudo (mockados + reais)
pytest tests/integration --real-api     # só os reais
```

Cada teste é pulado automaticamente se a chave correspondente não estiver no `.env`.

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
- [x] Publicação no YouTube (com trava por tipo; sobe como privado por padrão)

**Futuro**
- [ ] Análise de desempenho dos vídeos publicados para refinamento automático do pipeline
- [x] Detecção de tendências para adaptação dinâmica dos temas (Trends MCP + Gemini)