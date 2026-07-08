# Pilar Conformidade (a consciência)

Mantém o sistema **dentro das regras da plataforma de destino**. Ao contrário dos outros
pilares, a Conformidade **não produz nada** — ela **veta** e **marca**: decide quando o
disclosure de mídia sintética do YouTube se aplica, sinaliza quando a saída derrapa no
padrão de "conteúdo inautêntico" produzido em massa, confere que cada ativo tem origem
licenciada, veta temas inapropriados na borda da Descoberta, e guarda uma trilha de
auditoria por vídeo. Cruza os outros pilares como as Operações. Spec de referência:
`PILAR_7_COMPLIANCE.md` (raiz).

Dois princípios governam o pilar: **checagens objetivas bloqueiam, subjetivas avisam** —
um veto automático sobre julgamento de máquina mataria bons vídeos e faria desligarem o
pilar; e as **regras são versionadas** — quando a plataforma endurece uma política, apertar
o canal é **uma edição** e não uma caçada.

**Inerte por default:** o master `conformidade.ativo=false` ⇒ os hooks da Descoberta e da
Publicação são no-op ⇒ o comportamento é idêntico ao de hoje. Ligá-lo é uma decisão do
canal. **Sem segredo novo** — as camadas de julgamento reusam a integração Groq que já
existe no projeto, e falham **abertas** (um erro do Groq nunca bloqueia; blocos objetivos
não dependem dele).

## Fluxo

```
Descoberta (tema escolhido) → avaliar_tema  → Veredito (liberado | bloqueado | flag)
                                              bloqueado → dia pulado; flag → slot pendente

Publicação (run pronto) → avaliar_publicacao → Parecer (bloqueado + flags + disclosure)
  disclosure/licença (objetivas) bloqueiam · autenticidade/factual (subjetivas) avisam
```

Ambas as bordas escrevem a **trilha de auditoria** e são no-op quando o pilar está desligado.

## Módulos

| Arquivo | Papel |
|---|---|
| `configuracao.py` | `CONFORMIDADE_PADRAO` + enums (`MODOS_CHECK`/`ESTRATEGIAS`/`CHECAGENS`) + `mesclar_conformidade` + `UI_HINTS` (o *como* de cada checagem: bloquear vs. advisory + limiares). |
| `regras.py` | Conjunto de regras **versionado por tipo** (`tipos/<id>/conformidade/regras.json`): o *conteúdo* (regra de disclosure, listas de brand safety, mapa de licenças) + changelog + `publicar(regras, nota)`. |
| `auditoria.py` | Trilha **append-only por tipo** (`tipos/<id>/conformidade/auditoria.json`): cobre o veto de tema (Descoberta) e as checagens de publicação. |
| `parecer.py` | Formas de hand-off: `Veredito` (tema), `Parecer` (publicação), `Checagem` (auditoria). |
| `disclosure.py` | Objetiva: narração sintética + visual sintético/realista ⇒ disclosure exigido. |
| `licenciamento.py` | Objetiva: cada provedor de ativo (do sidecar) precisa estar no mapa de licenças. |
| `marca.py` | Brand safety do tema: lista de bloqueio (clear-cut) + Groq no limítrofe. |
| `autenticidade.py` | Duas camadas advisory: variação/persona (objetiva) + sameness vs. roteiros recentes (Groq). |
| `factual.py` | Precisão factual opcional (desligada por default), advisory, via Groq. |
| `conformidade.py` | Orquestrador: `avaliar_tema` / `avaliar_publicacao` / `modo_efetivo` (o rigor global modula os modos). |

## Onde encosta nos outros pilares

- **Descoberta** — `decidir_tema` chama `avaliar_tema` sobre o vencedor antes de gravar o
  slot: clear-cut bloqueia (dia pulado, auditado); limítrofe manda para o gate de revisão
  (`pendente`).
- **Publicação** — `publicador` chama `avaliar_publicacao` após a thumbnail, tanto em
  `publicar()` quanto em `publicar_aprovado()`: bloqueio objetivo barra o run
  (`bloqueado_conformidade`); flags advisory forçam a revisão humana.
- **Geração** — a checagem de autenticidade lê `geracao.variacao` e os roteiros dos sidecars
  recentes (nenhum campo novo é gravado a montante).
- **Controle** — aba **Conformidade** (config schema-driven + editor do conjunto de regras
  com changelog); flags no gate `/aprovacoes`; painel de auditoria na página do run.

## Rodar

As checagens rodam nas bordas da Descoberta/Publicação quando o pilar está ligado. Para
exercitar num shell:

```python
from config.tipos import carregar_tipo
from conformidade import conformidade
tipo = carregar_tipo("cetico_pratico")
conformidade.avaliar_tema(tipo, "um tema qualquer")            # Veredito
conformidade.avaliar_publicacao(tipo, "<pasta_do_run>", cfg_pub)  # Parecer
```

Testes: `pytest tests/test_conformidade*.py tests/test_{regras,auditoria,disclosure,licenciamento,marca,autenticidade,factual}.py`
(Groq e todos os clientes externos mockados).
