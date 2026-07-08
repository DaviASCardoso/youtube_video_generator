# Pilar Controle

A **superfície humana** do sistema: configura, dispara, observa, inspeciona e **avisa**.
Não tem lógica de pilar própria — renderiza formulários a partir do *schema* de cada
pilar e views a partir dos *records* que eles gravam, e relê sinais para o painel e as
notificações. A spec de referência é `PILAR_4_CONTROLE.md` (raiz).

Casa em dois lugares (inalterados): `api/` (web) e `config/` (camadas de config). O
entrypoint continua `uvicorn api.app:app` — o mesmo processo serve o painel **e** roda o
scheduler.

## Princípio: fino e schema-driven

Em vez de um `Form(...)` e um `<input>` por knob, o painel **gera** o formulário a partir
do dict de defaults do pilar (`*_PADRAO`) mesclado com o config salvo do tipo. Um knob
novo no PADRAO aparece sozinho, com o default visível e um selo quando o valor sobrescreve
o default.

- `api/formulario.py` — o motor: `arvore(padrao, atual, hints)` monta a árvore de
  `Campo`/`Grupo` (tipo inferido do tipo Python do default: bool→checkbox, int/float→
  number, list→lista, str→text/select/textarea, None→opcional); `reagrupar(form, padrao,
  hints)` reconstrói o dict aninhado do POST achatado, coagindo cada folha pelo tipo do
  default. O dict resultante é validado pelo Pydantic do pilar e salvo preservando os
  blocos irmãos.
- `api/templates/_form_schema.html` — a macro Jinja recursiva (`render_form`) que desenha
  a árvore (fieldset/details, selects, checkboxes, time, lista).
- **`UI_HINTS`** por pilar (em cada `<pilar>/configuracao.py`, e em `config/sistema.py`,
  `operacoes/notificacoes.py`, `api/routers/tipos.py` para a aba Config) mapeia `path
  pontuado → {rotulo, ajuda, min, max, passo, opcoes, avancado, multilinha, oculto}`.
  As `opcoes` reusam as tuplas de enum que os pilares já exportam.

Cada aba de config (`Config`, `Descoberta`, `Geração`, `Publicação`) e as `Configurações`
globais + a aba `Notificações` usam esse motor. Parity com os formulários hand-coded
antigos é provada por testes de round-trip (`tests/test_*_configuracao.py`,
`tests/test_config_tab_schema.py`).

## O que cada rota faz

- `api/routers/tipos.py` — lista/cria/duplica/renomeia/exclui tipos; renderiza a página de
  edição com abas; a aba **Config** (nome/ativo + groq/together/imagens/tts/pipeline/
  agendamento/youtube) é gerada por schema (`CONFIG_TAB_PADRAO` = `DEFAULT_CONFIG` menos os
  blocos de pilar); reinjeta descoberta/geração/publicação no salvar.
- `api/routers/{descoberta,geracao,publicacao}.py` — as abas dos pilares 1/2/3, geradas por
  schema, mais a observabilidade e os botões de cada um (aprovar tema, reexecutar,
  aprovar & publicar / verificar credencial).
- `api/routers/assets.py` — aba **Prompts**: editores de texto para todos os prompts
  (roteiro, imagem, cena, tendência/fit, metadados, thumbnail) + upload de PNGs.
- `api/routers/temas.py` — aba **Ideias** (pool manual/evergreen).
- `api/routers/configuracoes.py` — **Configurações globais** (sistema.json) + aba
  **Notificações** (config ntfy no sistema.json + status do canal + botão de teste).
- `api/routers/execucoes.py` — hub de **Execuções**: dashboard de saúde/custo/cota no topo,
  disparo (pipeline completo ou **só descoberta**), **cancelar** um run, histórico, detalhe
  com SSE ao vivo e playback do vídeo.
- `api/routers/aprovacoes.py` — **gate de aprovação unificado** (`/aprovacoes`): junta os
  temas `pendente` da Descoberta e os runs `aguardando_publicacao` da Publicação, com
  aprovar/rejeitar/editar. Delega às operações que já existem nos pilares.
- `api/auth.py` + `api/routers/auth.py` — gate de login single-admin (opcional, via
  `.env`), middleware ASGI puro que não quebra o SSE.

## Saúde e notificações (transversais, em `operacoes/`)

Ficam em Operações (transversal) para qualquer pilar poder usar sem importar a web:

- `operacoes/saude.py` — leitura **pura** dos sinais que o dashboard mostra: scheduler
  rodando, disco livre, credenciais (expirando/expirada), gasto do dia vs teto, cota vs
  cap, último publish por tipo, e a **saúde das raízes de armazenamento** (`caminhos_saude()`
  → cada raiz de `config/caminhos.py` existe e é gravável?). Não computa nem força nada. Uma
  raiz apontando para um mount (NAS) ausente/somente-leitura vira sinal no `/execucoes` (e um
  alerta `disco_baixo` no `verificar_e_alertar`), em vez de estourar no meio de um run.
- `operacoes/notificacoes.py` — canal **ntfy** (`emitir(categoria, titulo, msg)`, POST via
  urllib). Config tunável (liga/desliga por categoria, prioridade, horas de silêncio) no
  `sistema.json`, bloco `notificacoes`; os campos sensíveis (server/topic/token) no `.env`
  (`NTFY_SERVER`/`NTFY_TOPIC`/`NTFY_TOKEN`). Política default **silenciosa**: interruptor
  geral desligado; ao ligar, só as categorias de atenção vêm em `high` (run falhou,
  credencial, cota, disco, scheduler, revisão pendente); as de rotina ficam off.
  `emitir` é chamado nos pontos-fonte que já existem (run falhou, cap/credencial na
  Publicação, tema/run pendente) + um job periódico de saúde (`scheduler._job_saude`) para
  disco baixo / credencial expirando.

## Ações que Control aciona (nunca executa)

Triggering e cancelamento pedem ao Operações (`operacoes/scheduler.py`):
`disparar_agora` (pipeline completo), `descobrir_agora` (só decisão do tema),
`reexecutar_agora` (retoma do checkpoint), `publicar_agora` (aprovar/reconciliar),
`cancelar` (cancelamento **cooperativo** — o pipeline checa entre estágios e aborta na
próxima fronteira; não há kill de thread). Tudo respeita o invariante de um-run-por-tipo.
