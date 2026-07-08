# Pilar Operações (transversal)

Mantém o sistema **rodando sem supervisão**: é o **relógio** que agenda os jobs de todo
pilar, o **orquestrador reativo** que encadeia descoberta → geração → publicação → feedback,
e o **motor inteligente de resposta a falhas** que classifica cada erro e casa a resposta
à classe. Também recupera runs interrompidos por reboot, coleta sinais de saúde e emite
eventos para o Controle. É transversal: não contém a lógica dos pilares — pede que eles
façam o trabalho e reage ao resultado.

## Módulos

- **`scheduler.py`** — um `BackgroundScheduler` (APScheduler in-memory) iniciado/parado
  pelo `lifespan` do FastAPI. Por tipo: o job de **geração** (no horário/fuso configurado)
  e o de **descoberta** (`antecedencia_horas` antes), cada um ligável por
  `operacao.jobs.{geracao,descoberta}`. Globais: `_job_saude` (6/6h — grava a batida do
  scheduler e alerta disco/credencial) e `_job_feedback` (diário — ingere+processa por tipo
  ativo, respeitando `operacao.jobs.feedback`). Além dos disparos manuais
  (`disparar_agora`/`descobrir_agora`/`reexecutar_agora`/`publicar_agora`), do
  cancelamento cooperativo (`cancelar`) e do **reagendamento de runs adiados**
  (`reagendar_adiado`, injetado via `definir_reagendador`).
- **`execucoes.py`** — o **caminho único** de execução (cron e "executar agora" produzem o
  mesmo histórico/log). `executar_com_captura()` roda `gerar_video` sob captura de stdout,
  registra custo + observabilidade do motor, publica se configurado, e converte as exceções
  tipadas do motor em estado: `Deferir`/`OrcamentoExcedido` → **`adiado`** (marca +
  reprograma para a janela de reset + escala), `ResilienciaEsgotada`/`HaltDestino` →
  **`dead_letter`** (escala `job_dead_letter`, re-executável pelo painel). Também
  `HistoricoExecucoes` (com `retentativas`/`failover`/`classe`/`adiado_para`/`recuperado`)
  e o transmissor de logs ao vivo.
- **`resiliencia.py`** — o **motor**. `classificar(erro)` mapeia todo erro numa das classes
  `transitorio` (timeout/conn/5xx/429-rate — a única retryável) · `permanente` (4xx≠auth/
  quota, validação — falha rápido) · `auth` (401/403, refresh-token — tenta refresh, senão
  halt) · `quota` (429-quota, cap de pilar — defere para a janela) · `recurso` (disco/NAS
  cheio, OOM — halt), por **duck-typing** (status HTTP + nomes de tipo/módulo), sem importar
  SDKs. `executar(fn, …)` é o policy-engine: backoff honrado (`Retry-After`) + jitter só para
  transitório, teto de retry por estágio que **não fura o orçamento** (`custo_ok`),
  retry→**failover** para o alternativo do pilar, **circuit breaker** por provedor,
  tratamento **adaptativo** (provedor flaky → menos retries), e as exceções tipadas
  (`Deferir`/`HaltDestino`/`ResilienciaEsgotada`) que sobem para a orquestração.
- **`circuitos.py`** — o circuit breaker **persistido** (`execucoes/circuitos.json`, mesmo
  padrão JSON+lock de `GastoDiario`/`QuotaDiaria`): `fechado`/`aberto`/`meio_aberto`
  derivados de falhas consecutivas + cooldown; sobrevive a restart.
- **`recuperacao.py`** — `recuperar_execucoes()`: na subida, varre o histórico por runs
  presos em `executando` (órfãos de um reboot) e os re-enfileira **reusando a pasta** (o
  checkpoint da Geração retoma de onde parou). Sem jobstore/DB — só o histórico.
- **`saude.py`** — leitura pura dos sinais (scheduler up + **batida**, disco, credenciais,
  gasto/orçamento, cota, último publish) para o dashboard do Controle e para
  `verificar_e_alertar()` (o que vale um push).
- **`notificacoes.py`** — canal ntfy (o Controle consome). `emitir(categoria, …)` é no-op
  sem `NTFY_TOPIC`; categorias críticas (inclui `job_dead_letter`) furam as horas de
  silêncio.

## Configuração (bloco `operacao` por tipo)

`operacoes/configuracao.py` (`OPERACAO_PADRAO` + `mesclar_operacao` + `UI_HINTS`, enums
importados por `api/schemas.py`, espelhado em `DEFAULT_CONFIG`, preservado no salvar da aba
Config, editado na aba **Operação** schema-driven): `jobs.*` (enablement por pilar),
`caps_por_estagio` (teto de retry — mais apertado nos caros), `backoff` (base/teto/jitter),
`circuito` (limiar/cooldown/janela), `failover`, `falha_parcial` (degradar|falhar),
`defer_horas` (quota/orçamento).

**Os limites moram nos pilares donos** (orçamento em `geracao`, cota em `publicacao`, sample
floor em `feedback`) — Operações só **lê e enforça**, transformando "cap batido" em
defer+escalada. **Default = comportamento de sempre**: 3 retries transitórios no roteiro,
backoff base 2s, failover aos mesmos alternativos, circuito que não dispara sob provedores
que acertam de 1ª. Nenhuma credencial nova — reusa o APScheduler, o service runner e o ntfy.
