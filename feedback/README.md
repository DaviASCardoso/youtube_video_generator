# Pilar Feedback (Retorno)

Fecha o laço com o **desempenho real**: puxa as métricas de cada vídeo publicado,
atribui o resultado aos inputs que o produziram, rola isso em **findings** por dimensão
e **aplica** os findings de volta na Descoberta/Geração/Publicação — para o sistema
fazer mais do que funciona. Spec de referência: `PILAR_5_FEEDBACK.md` (raiz).

Duas metades de peso igual: **coletar** (ingerir → atribuir → agregar) e **aplicar**
(rotear findings em ajustes numéricos limitados no config **ou** em guia de prompt
traduzida por LLM). Dois princípios: **eficiência** (re-poll só na agenda de maturação,
nunca re-puxar/recomputar dado inalterado) e **configurabilidade** (métricas, agenda,
piso amostral e agressividade da aplicação editáveis no painel, defaults conservadores).

**Inerte por default:** `feedback.destinos.youtube.ativo=false` ⇒ nenhuma chamada de
analytics; a aplicação é `advisory` por alvo ⇒ nada muda sem aprovação humana. Ligar o
pilar exige habilitar a YouTube Analytics API e reconsentir o escopo
`yt-analytics.readonly` (mesma credencial OAuth por tipo — **sem segredo novo**).

## Fluxo

```
published-record + sidecar → ingestão → atribuição → agregação → FINDINGS
FINDINGS → roteador determinístico → ┌ numérico → ajuste limitado no config ┐→ [advisory: propõe → humano aprova | auto] → Descoberta/Geração/Publicação
                                     └ textual  → tradutor (Groq) → bloco de guia ┘
```

## Módulos

| Arquivo | Papel |
|---|---|
| `configuracao.py` | `FEEDBACK_PADRAO` + enums + `mesclar_feedback` + `UI_HINTS` (bloco `feedback` por tipo). |
| `armazenamento.py` | Stores por tipo (JSON+lock) em `tipos/<id>/feedback/`: `metricas`, `findings`, `propostas`, `aplicados`. |
| `analytics_youtube.py` | Cliente Analytics v2 + Data v3, reusando `publicacao.youtube.autenticar`. Degrada em `None`. |
| `destinos/{base,youtube}.py` | Destino de analytics plugável (contrato `metricas_do_video`/`checar`). |
| `maturacao.py` | Agenda de re-poll (≈24h/72h/7d/30d, depois para) — funções puras. |
| `ingestao.py` | Por tipo, puxa o marco devido de cada vídeo publicado e guarda (curva inclusa). |
| `atribuicao.py` | Junta a performance aos inputs (fonte/categoria/voz/modo_visual/hook/título/horário/duração), lido do que já foi gravado. |
| `agregacao.py` | Rollup por dimensão → findings **cientes do tamanho de amostra** (piso, confiança). |
| `roteador.py` | Mapa **estático** dimensão→destino; propostas numéricas/set **limitadas**. |
| `traducao.py` | Groq reconcilia+reescreve um bloco de guia (top-K, cap). O LLM só traduz, nunca roteia. |
| `guia.py` | Bloco de guia versionado (`tipos/<id>/guia/<nome>.json`) + injetor `compor` (5 prompts) + veto/fix. |
| `aplicacao.py` | Aplica proposta (numérico/set/guia) **reversível**; gate advisory (`aprovar`/`rejeitar`). |
| `feedback.py` | Orquestrador `processar(tipo)`: atribui→agrega→roteia→propõe (ou auto-aplica). |
| `experimentos.py` | Costura, off por default. |

## Onde encosta nos outros pilares

- **Prompts:** `guia.compor(assets_dir, nome, base)` injeta o bloco aprendido nos 5
  pontos de leitura de prompt (roteiro/visual da Geração, fit da Descoberta,
  metadados/thumbnail da Publicação). Bloco ausente ⇒ prompt idêntico ao de hoje.
- **Config numérico:** os alvos `descoberta.evergreen_ratio`, `publicacao.timing.horario`,
  `geracao.roteiro.duracao_alvo_seg` (+ set-value em `tts.voz`/`geracao.visuais.fundo`
  — a camada de fundo, IA/Pexels — /`publicacao.thumbnail.ativo`) recebem ajuste limitado e reversível.
- **Operações:** `scheduler._job_feedback` (diário) chama `ingestao.ingerir` +
  `feedback.processar` por tipo ativo.
- **Controle:** aba **Feedback** (config schema-driven) no editar-tipo e a página
  standalone **/feedback** (findings, curvas, performance, propostas com aprovar/rejeitar,
  guia com veto/fix, histórico aplicado com reverter).

## Rodar

Ingestão e processamento acontecem no job diário. Para exercitar num shell:

```python
from config.tipos import carregar_tipo
from feedback import ingestao, feedback
tipo = carregar_tipo("cetico_pratico")
ingestao.ingerir(tipo)   # precisa do destino ligado + credencial com o escopo de analytics
feedback.processar(tipo) # gera findings/propostas
```

Testes: `pytest tests/test_feedback*.py tests/test_{ingestao,maturacao,atribuicao,agregacao,roteador,traducao,aplicacao,armazenamento,guia,analytics_youtube,experimentos}.py`
(todos os clientes externos — Analytics/Data API, Groq — mockados).
