# Pilar Operações (transversal)

Mantém o sistema **rodando sem supervisão**: agendamento, orquestração de execução, captura de erros e — no futuro — retries, alertas, segredos e limites de custo/runtime.

Módulos:
- `scheduler.py` — APScheduler: um job por tipo + o job global diário de tendências.
- `execucoes.py` — `executar_com_captura()` (caminho único do cron e do "executar agora"), `HistoricoExecucoes` e o transmissor de logs ao vivo.

Natureza transversal: o **histórico de execuções** e os **logs ao vivo** vivem aqui, mas são exibidos pelo Controle (painel web). Segredos hoje vêm do `.env` na raiz (cada módulo faz `load_dotenv`); uma futura camada central de segredos e de limites de custo aterrissa neste pilar.
