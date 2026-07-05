# 🎬 Gerador Automático de Vídeos para YouTube

> **Status:** Em desenvolvimento ativo

## Visão Geral

Pipeline 100% automatizado para geração e publicação periódica de vídeos longos no YouTube. Cada etapa é delegada a um modelo de IA especializado — do roteiro à publicação — sem intervenção humana.

O sistema suporta múltiplos **tipos de vídeo** rodando lado a lado (ex: canais ou personas diferentes), cada um com seu próprio agendamento, prompts, voz, configurações de geração, descoberta de temas e pool de ideias. Cada tipo vive em sua própria pasta dentro de `tipos/`.

Um **painel web** (`uvicorn api.app:app`) permite controlar tudo isso sem editar arquivos JSON ou rodar scripts manualmente: criar/editar/duplicar/renomear/excluir tipos, editar prompts e configurações com validação, ajustar a descoberta e o pool de ideias, disparar execuções manuais e acompanhar logs ao vivo e o histórico de execuções.

## Arquitetura: os sete pilares

O sistema é organizado em **sete pilares**, cada um com uma responsabilidade clara e um lar próprio no repositório. Este é o mapa mental do projeto — comece por aqui.

| Pilar | Responsabilidade | Lar |
|---|---|---|
| **Descoberta** | Decidir o que fazer: reunir sinais de várias fontes, avaliar fit, deduplicar e decidir **um único tema** por tipo a cada ciclo. | `descoberta/` |
| **Geração** | Transformar o tema no artefato de mídia final: roteiro, imagens, narração e montagem do vídeo. | `geracao/` |
| **Publicação** | Levar o artefato até a plataforma: metadados, upload, visibilidade. | `publicacao/` |
| **Controle** | Superfície humana: painel web, camadas de configuração, histórico e logs. | `api/` + `config/` |
| **Feedback** | Fechar o ciclo com o desempenho real: analytics → entradas que os produziram. | `feedback/` *(placeholder)* |
| **Operações** | Rodar sem supervisão: agendamento, orquestração, erros, segredos, custo. *(transversal)* | `operacoes/` |
| **Conformidade** | Ficar dentro das regras da plataforma: divulgação de mídia sintética, autenticidade. | `conformidade/` *(placeholder)* |

Cada pilar tem um `README.md` próprio detalhando seus módulos. **Controle** mantém dois lares existentes e já bem nomeados (`api/` para a app web, `config/` para as camadas de configuração). **Feedback** e **Conformidade** ainda não têm código — são lares reservados. Pastas de dados de runtime (`output/`, `execucoes/`, `tendencias/`) e o conteúdo por tipo (`tipos/`) não são código e ficam na raiz.

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
| Descoberta de temas | Trends MCP, YouTube, Google Trends, Reddit, Wikipédia + Gemini 3.5 Flash |
| Narração | Google Cloud TTS |
| Publicação | YouTube Data API v3 |
| Painel web | FastAPI + Jinja2 + HTMX |
| Agendamento | APScheduler |

## Descoberta de temas (por tipo)

Cada tipo decide sozinho **o que produzir a seguir**. A Descoberta roda
`antecedencia_horas` antes do horário de geração do tipo (configurável no painel)
e decide **um único tema**:

1. Reúne candidatos das fontes ativas: **Trends MCP**, **YouTube** (Data API v3),
   **Google Trends** (pytrends-modern), **Reddit** (feeds .rss), **Wikipédia**
   (Pageviews) e o **pool de ideias** manuais/evergreen. Cada fonte liga/desliga.
2. Deduplica contra o que já foi feito (janela e estratégia configuráveis).
3. Faz um pré-rank barato e avalia o **fit** (Gemini) só nos top candidatos —
   aceita/rejeita com um score, guiado por `system_prompt_tendencia.txt`.
4. Seleciona um por pontuação ponderada (sinal + fit + frescor) e o deposita no
   slot do tipo. Em modo **revisar**, o tema fica pendente até você aprovar.
5. No horário de geração, o vídeo é feito a partir desse tema decidido.

Tudo é configurável na aba **Descoberta** de cada tipo (fontes e seus parâmetros,
score mínimo, dedupe, pesos de seleção, mix trending/evergreen, gate de revisão,
retenção, orçamento de avaliação e antecedência). As ideias manuais/evergreen
ficam na aba **Ideias**. Requer `TRENDS_MCP_API_KEY` e `GEMINI_API_KEY` no `.env`
(YouTube precisa do OAuth do tipo; Reddit e Wikipédia são sem chave).

## Geração (por tipo)

A Geração transforma o tema decidido no vídeo final por **estágios explícitos e
checkpointados** — roteiro → plano visual → visuais → narração → montagem — cada um:

1. **Reaproveita** o artefato se já existe e valida (resumabilidade): uma reexecução
   retoma de onde parou, sem refazer — e sem pagar de novo — o que já ficou pronto.
2. Passa por um **gate** de qualidade antes de o próximo estágio gastar.
3. Roda atrás de um **contrato de provedor** por papel (roteiro/visuais/narração),
   deixando uma costura limpa para novos provedores (ex.: ElevenLabs).
4. **Registra o custo** por etapa e respeita o **orçamento** por vídeo/dia (degrada
   para um provedor mais barato/placeholder, ou para).
5. **Degrada em vez de quebrar**: retry+backoff, provedor de fallback, placeholder;
   a narração cai para a **voz secundária**.

Ainda **varia deliberadamente** aberturas/estrutura/estilo/música (anti-repetição) e
grava, ao lado do `video_final.mp4`, um `sidecar.json` (tema, roteiro, duração,
provedores e custos) que a Publicação consome. Tudo é editável na aba **Geração** de
cada tipo (provedores por estágio, tamanho/tom do roteiro, modo/estilo dos visuais,
voz, legendas, música/intro/outro, variação, orçamento e checkpoint), que também
mostra a **observabilidade** das últimas execuções (custo/provedor por etapa) e um
botão **Reexecutar** que retoma a mesma pasta.

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
python -m publicacao.youtube auth --tipo cetico_pratico
```

Depois disso, ligue **"Publicar automaticamente no YouTube após gerar"** na aba Config do tipo. Recomendação: comece com a visibilidade em **`private`** — o vídeo sobe, mas só você vê, e você promove a público manualmente no YouTube Studio. O título vem do tema e a descrição do roteiro + a "descrição base" do config + `#Shorts` + as tags. A URL publicada aparece no histórico de execuções.

Para publicar um vídeo já gerado na mão:

```
python -m publicacao.youtube publicar caminho/para/video_final.mp4 --tipo cetico_pratico
```

⚠️ **Gotcha dos 7 dias:** enquanto o app OAuth estiver em modo **"Testing"** no Google Console, o token expira em 7 dias e a publicação para de funcionar. Ponha o app em **"In production"** (aceitando a tela de "app não verificado" no consentimento único) para tokens duráveis. Se o token expirar, rode o comando `auth` de novo.

## Testes

A pasta `tests/` tem uma suíte de testes unitários (pytest) para toda a lógica fora da camada web — as camadas de configuração (`config/`) e os pilares de código (`geracao/`, `descoberta/`, `publicacao/`, `operacoes/`). Todas as chamadas de API externas (Groq, Together, Google TTS, Pexels, Trends MCP, Gemini) são mockadas, então a suíte roda offline, rápida e sem gastar cota. Nenhum teste toca nas pastas reais (`tipos/`, `execucoes/`, `tendencias/`) nem no `config/sistema.json`.

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
- [x] Geração em estágios checkpointados (reaproveita artefatos, gates de qualidade, provedores plugáveis, custo/orçamento, variação, degradação graciosa, sidecar)
- [x] Suporte a múltiplos tipos de vídeo (agendamento, prompts, voz e fila de temas independentes por tipo)
- [x] Interface web para controle e monitoramento
- [x] Publicação no YouTube (com trava por tipo; sobe como privado por padrão)

**Futuro**
- [ ] Análise de desempenho dos vídeos publicados para refinamento automático do pipeline
- [x] Descoberta de temas por tipo (5 fontes de sinal + pool, fit com score, dedupe, seleção ponderada, gate de revisão)