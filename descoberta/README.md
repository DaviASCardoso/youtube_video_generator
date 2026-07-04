# Pilar Descoberta

Decide **o que produzir**: busca sinais (tendências), transforma em tema no contexto do canal, deduplica contra o que já foi usado e mantém a fila priorizada.

Módulos:
- `trends.py` — cliente do Trends MCP (tendências do dia).
- `gemini.py` — transforma uma tendência em tema (Gemini). Cliente LLM genérico, hoje usado só aqui.
- `tendencias.py` — orquestra a coleta diária + `HistoricoTendencias` (dedupe por tipo).
- `temas.py` — `FilaDeTemas`, a fila priorizada por tipo. Consumida pelo Controle via `config/tipos.py`, que expõe `TipoVideo.temas` (aresta Controle→Descoberta).

Runner: `python -m descoberta.tendencias` (dry-run; `--commit` grava).
Escreve em `tendencias/` (dedupe) e nas filas `tipos/<id>/temas.json`.
