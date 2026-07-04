# Pilar Descoberta

Decide **o que produzir a seguir**: reúne candidatos de várias fontes de sinal,
avalia o fit de cada um para o tipo, deduplica contra o que já foi feito e decide
**um único tema** por tipo — pronto para a produção consumir. Não mantém fila
drenável: a saída é sempre um tema decidido por ciclo (em modo revisão, ele fica
pendente até aprovação). Dois princípios: **eficiência** (o passo caro — LLM — só
nos top contenders) e **configurabilidade** (tudo no bloco `descoberta` por tipo).

Fluxo: `fontes ativas → candidatos → dedup → pré-rank barato → fit dos top N →
seleção ponderada → 1 tema decidido → (gate) pronto|pendente`.

Módulos:
- `configuracao.py` — `DESCOBERTA_PADRAO` (defaults) + enums; fonte da verdade do
  schema do bloco `descoberta` (o Controle importa os enums para validar).
- `candidato.py` — `Candidato` (forma normalizada) e `Decisao` (hand-off).
- `fontes/` — fontes plugáveis sob um contrato comum (`base.py`): `trends_mcp`,
  `youtube` (Data API v3), `google_trends` (pytrends-modern), `reddit` (.rss),
  `wikipedia` (Pageviews) e `pool` (ideias manuais/evergreen do temas.json). Cada
  fonte tem liga/desliga e degrada para nada em vez de quebrar o ciclo.
- `fit.py` + `gemini.py` — avaliação de fit por tipo (aceito + score 0-100), o
  passo caro; usa o critério/persona de `system_prompt_tendencia.txt`.
- `dedup.py` — repetição por estratégia exato/token numa janela configurável.
- `selecao.py` — pontuação sinal+fit+frescor (decaimento por meia-vida).
- `balanco.py` — decide trending vs evergreen do ciclo pelo `evergreen_ratio`.
- `estado.py` — por tipo: slot decidido, buffer de retenção e histórico (observabilidade).
- `descoberta.py` — orquestrador `decidir_tema(tipo)`.
- `tendencias.py` — `HistoricoTendencias` (dedupe de sinais consumidos) + o prompt
  de critério do tipo.
- `temas.py` — `FilaDeTemas`, agora o **pool de ideias** de entrada (manual/evergreen),
  distinguido pelo campo `fonte`. Consumido pela fonte `pool` e pelo Controle.

Runner: `python -m descoberta.descoberta` (dry-run; `--commit` grava o slot).
Escreve em `tendencias/` (dedupe) e em `tipos/<id>/descoberta_*.json` (slot,
buffer, histórico — gitignored). *Quando* rodar é decisão de Operações (agendado
`antecedencia_horas` antes da geração do tipo).
