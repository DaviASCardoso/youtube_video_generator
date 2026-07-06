# 🎬 Gerador Automático de Vídeos para YouTube

> **Status:** Em desenvolvimento ativo

## Visão Geral

Pipeline 100% automatizado para geração e publicação periódica de vídeos longos no YouTube. Cada etapa é delegada a um modelo de IA especializado — do roteiro à publicação — sem intervenção humana.

O sistema suporta múltiplos **tipos de vídeo** rodando lado a lado (ex: canais ou personas diferentes), cada um com seu próprio agendamento, prompts, voz, configurações de geração, descoberta de temas e pool de ideias. Cada tipo vive em sua própria pasta dentro de `tipos/`.

Um **painel web** (`uvicorn api.app:app`) permite controlar tudo isso sem editar arquivos JSON ou rodar scripts manualmente: criar/editar/duplicar/renomear/excluir tipos, editar prompts e todas as configurações (os formulários são **gerados a partir do schema** de cada pilar — um knob novo aparece sozinho), ajustar a descoberta e o pool de ideias, disparar execuções (pipeline completo ou só descoberta), **cancelar** um run, aprovar temas/vídeos num **gate de aprovação** unificado, ver um **painel de saúde/custo/cota** e receber **notificações no celular** (ntfy) — além de acompanhar logs ao vivo e o histórico.

## Arquitetura: os sete pilares

O sistema é organizado em **sete pilares**, cada um com uma responsabilidade clara e um lar próprio no repositório. Este é o mapa mental do projeto — comece por aqui.

| Pilar | Responsabilidade | Lar |
|---|---|---|
| **Descoberta** | Decidir o que fazer: reunir sinais de várias fontes, avaliar fit, deduplicar e decidir **um único tema** por tipo a cada ciclo. | `descoberta/` |
| **Geração** | Transformar o tema no artefato de mídia final: roteiro, imagens, narração e montagem do vídeo. | `geracao/` |
| **Publicação** | Levar o artefato até a plataforma: metadados, upload, visibilidade. | `publicacao/` |
| **Controle** | Superfície humana **fina e schema-driven**: painel web (config, disparo, aprovação, dashboard, notificações), camadas de configuração, histórico e logs. | `api/` + `config/` |
| **Feedback** | Fechar o ciclo com o desempenho real: ingerir analytics, atribuir aos inputs, agregar em findings e **aplicar** (ajuste numérico limitado no config **ou** guia de prompt traduzida por LLM), advisory por default. | `feedback/` |
| **Operações** | Rodar sem supervisão: agendamento, orquestração, erros, segredos, custo. *(transversal)* | `operacoes/` |
| **Conformidade** | Ficar dentro das regras da plataforma: divulgação de mídia sintética, autenticidade. | `conformidade/` *(placeholder)* |

Cada pilar tem um `README.md` próprio detalhando seus módulos. **Controle** mantém dois lares existentes e já bem nomeados (`api/` para a app web, `config/` para as camadas de configuração). **Conformidade** ainda não tem código — é um lar reservado. Pastas de dados de runtime (`output/`, `execucoes/`, `tendencias/`, e por tipo `tipos/<id>/feedback/` e `tipos/<id>/guia/`) e o conteúdo por tipo (`tipos/`) não são código e ficam na raiz.

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

## Publicação (por tipo)

A Publicação leva o vídeo pronto (o `video_final.mp4` + o `sidecar.json`) até a
plataforma, tudo editável na aba **Publicação** de cada tipo:

1. **Metadados otimizados por Groq** — o mesmo LLM do roteiro transforma tema + roteiro
   em título, descrição e tags voltados para clique e busca (o tema **não** é o título).
   Sempre ligado; tom, moldes e estratégia de tags são configuráveis.
2. **Thumbnail** (opcional, por tipo) — fundo por IA (FLUX) **ou** banco de imagens
   (Pexels), com o texto de chamada (gerado por Groq) composto por cima com fonte/cor/
   posição/contorno configuráveis.
3. **Destinos plugáveis** — cada destino tem seu liga/desliga e sua credencial isolada;
   YouTube está ligado, TikTok/Reels/Kwai são costura para depois. Uma credencial
   expirada/prestes a expirar é **surfada** no painel, não falha calada.
4. **Timing** — imediato (default) ou agendado (sobe privado e o YouTube publica no
   horário de go-live configurado, via `publishAt`).
5. **Visibilidade & disclosure** — privacidade (default public), audiência e a flag de
   mídia sintética (default ligada).
6. **Gate de revisão** — auto-publica (default) ou **revisar** (o vídeo espera aprovação
   no painel antes de ir ao ar).
7. **Eficiência** — nunca sobe o mesmo vídeo duas vezes (idempotência por
   published-record), respeita uma **cota diária por credencial** (default 5 uploads/dia,
   adia o excedente) e não refaz metadados/thumbnail que já existem.
8. **Observabilidade** — cada publicação registra destino, id, URL, visibilidade e cota
   no histórico; um destino que falha degrada sozinho, os outros seguem.

Com a config default **nenhum tipo publica** (destino desligado) — igual a hoje. Para
publicar, ligue o destino YouTube na aba Publicação.

### Credenciais do YouTube

Cada tipo usa seu **próprio projeto Google Cloud** (um por canal, para isolar a cota de upload), então as credenciais são **por tipo**:

- `tipos/<id>/youtube_client_secret.json` — o OAuth client (Desktop app) baixado do projeto daquele canal. Se ausente, cai no `client_secret_youtube.json` da raiz.
- `tipos/<id>/youtube_token.json` — criado no primeiro consentimento e reusado depois (gitignored).

**Consentimento único** (abre o navegador, você autoriza o canal e o token é salvo):

```
python -m publicacao.youtube auth --tipo cetico_pratico
```

Para publicar um vídeo já gerado na mão:

```
python -m publicacao.youtube publicar caminho/para/video_final.mp4 --tipo cetico_pratico
```

⚠️ **Gotcha dos 7 dias:** enquanto o app OAuth estiver em modo **"Testing"** no Google Console, o token expira em 7 dias e a publicação para de funcionar. Ponha o app em **"In production"** (aceitando a tela de "app não verificado" no consentimento único) para tokens duráveis. Se o token expirar, rode o comando `auth` de novo.

## Controle (o painel)

O painel é a superfície humana (Pilar 4 — spec `PILAR_4_CONTROLE.md`, detalhes em `api/README.md`). Ele **não** tem lógica própria: renderiza formulários a partir do schema de cada pilar e views a partir dos records que eles gravam.

- **Formulários gerados por schema** — todas as abas de config (Config, Descoberta, Geração, Publicação), as Configurações globais e a aba Notificações são desenhadas por `api/formulario.py` a partir do dict de defaults do pilar + um mapa `UI_HINTS`. Cada campo mostra seu default e marca quando você o sobrescreveu; um knob novo no pilar aparece no painel sem mexer no Controle.
- **Gate de aprovação** (`/aprovacoes`) — junta num lugar só os temas decididos em modo revisão (Descoberta) e os vídeos prontos aguardando publicação (Publicação), com aprovar / rejeitar / editar.
- **Painel de saúde/custo/cota** (no topo de Execuções) — scheduler rodando?, disco livre, gasto do dia, status das credenciais, cota/orçamento por tipo, último publish, e se o login e o ntfy estão configurados. Só lê sinais; não força nada.
- **Disparo e cancelamento** — dispare o pipeline completo, **só a descoberta** (decide o tema sem gerar), reexecute retomando do checkpoint, ou **cancele** um run em andamento (o cancelamento é cooperativo: para na próxima fronteira de estágio).
- **Notificações no celular (ntfy)** — aba **Notificações** nas Configurações. O ntfy é um pub-sub HTTP grátis: um POST num tópico chega no app do celular, sem conta nem chave no servidor público. Configure `NTFY_SERVER` (default `https://ntfy.sh`), `NTFY_TOPIC` (escolha algo **impossível de adivinhar** — no servidor público ele funciona como senha) e, opcional, `NTFY_TOKEN` no `.env`; os liga/desliga por evento, a prioridade e as horas de silêncio ficam no painel. A política default é **silenciosa** (o interruptor geral vem desligado); ao ligar, só o que pede atenção avisa em prioridade alta — run que falhou, credencial expirando, cota/disco no limite, scheduler parado, item na fila de aprovação —, enquanto sucessos de rotina ficam desligados (o tier grátis é 250 msgs/dia). Há um botão de teste. Sem `NTFY_TOPIC`, nada é enviado.

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
- [x] Publicação config-driven por tipo (metadados otimizados por Groq, thumbnail FLUX/Pexels + texto, destinos plugáveis com credencial isolada, agendamento, disclosure, gate de revisão, idempotência e cota diária)

**Futuro**
- [ ] Análise de desempenho dos vídeos publicados para refinamento automático do pipeline
- [x] Descoberta de temas por tipo (5 fontes de sinal + pool, fit com score, dedupe, seleção ponderada, gate de revisão)