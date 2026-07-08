# Pilar Geração

Transforma o **tema decidido** pela Descoberta no **artefato de mídia final**: um
`video_final.mp4` + um `sidecar.json` que descreve o vídeo (tema, roteiro, duração,
`modo_visual` (fonte do fundo usada), `hook` (abertura do roteiro), provedores/custos)
e serve de handoff para a Publicação e o Feedback.

A spec de referência é `PILAR_2_GERACAO.md` (raiz), sob dois princípios:
**eficiência** (nunca pagar duas vezes; nunca pagar uma etapa antes de validar a
anterior) e **configurabilidade** (todo provedor/parâmetro/toggle é editável no
painel, na aba "Geração").

## Camadas visuais (compostas e independentes)

O visual são **três camadas independentes** (substituem os dois modos empacotados;
`imagens.modo` virou só a fonte de migração). Cada uma liga/desliga e configura sozinha
no painel; os defaults (`"auto"`) reproduzem os dois presets de antes, migrando do
legado `imagens.modo` (`ia` → fundo IA + personagem off; `personagem` → fundo Pexels
+ personagem on). Qualquer combinação é possível.

- **Fundo** (`geracao.visuais.fundo`: `auto`|`ia`|`pexels`) — a fonte do backdrop,
  independente do personagem. O provedor de visuais **segue a fonte do fundo**
  (`provedor: "auto"` → `ia`→flux, `pexels`→pexels).
- **Personagem** (`geracao.visuais.personagem`: `auto`|`sim`|`nao`) — camada de PNG do
  personagem, composta pelo pipeline sobre qualquer fundo; posição/tamanho/margens em
  `imagens.personagem.*`. A **emoção por cena** é planejada como camada à parte: no fundo
  Pexels vem do próprio plano de cena (1 chamada); no fundo por IA é planejada em separado
  (`generate_scene.planejar_emocoes`, checkpoint `emocoes.txt`) — então um fundo por IA
  também tem expressão por cena, não um `neutro` fixo.
- **Legenda** (`geracao.legendas`) — burn-in opcional com fonte/cor/posição/contorno
  (as mesmas alavancas do texto da thumbnail).

## Pipeline em estágios

`pipeline.gerar_video(tema, tipo, output_path, ledger=None)` roda estágios explícitos
— **roteiro → plano visual → visuais → narração → montagem** — e cada um:

- **reaproveita** o artefato se já existe e valida (`checkpoint.py`) — resumabilidade;
- passa por um **gate** de qualidade antes de o próximo estágio gastar (`gates.py`);
- roda atrás de um **contrato de provedor** por papel (`provedores/`);
- **registra o custo** num `Ledger` e respeita o **orçamento** (`custo.py`);
- **degrada em vez de quebrar**: retry+backoff, provedor de fallback, placeholder.

## Módulos

Fonte da verdade da config e helpers do pipeline:
- `configuracao.py` — `GERACAO_PADRAO`, enums e `mesclar_geracao()` (bloco `geracao` por tipo).
- `checkpoint.py` — reaproveitamento de artefatos (existe + válido + toggle).
- `gates.py` — validação estrutural entre estágios (roteiro/plano/narração/visuais).
- `custo.py` — tabelas-estimativa, `Ledger`, gasto diário e `checar_orcamento()`.
- `variacao.py` — variação deliberada de abertura/estrutura/estilo/música (0 = idêntico; semeável).
- `sidecar.py` — escreve/lê o `sidecar.json` (handoff para a Publicação e o Feedback; grava `modo_visual`/`hook`).
- `legendas.py` — SRT + burn-in opcional (default off) com estilo de fonte/contorno.
- `pipeline.py` — `gerar_video()`: orquestra os estágios acima.

Provedores plugáveis por papel (`provedores/`):
- `base.py` — registro `(papel, nome) → provedor`; `obter()`, `provedores_de()`, `provedor_visuais_para_fundo()`.
- `roteiro_groq.py` — roteiro via Groq.
- `visuais_flux.py` — plano (prompts) + render por IA (Together/FLUX), fundo "ia".
- `visuais_pexels.py` — plano (emoção+busca) + foto Pexels de fundo (**só o fundo**; o personagem é camada do pipeline), fundo "pexels".
- `narracao_google.py` — narração via Google TTS (com override de voz para o fallback).
- *(seam documentado: ElevenLabs entra como `(narracao, "elevenlabs")` sem tocar no pipeline.)*

Chamadas externas concretas embrulhadas pelos provedores:
- `generate_script.py` / `generate_scene.py` — chamadas Groq (roteiro e plano).
- `generate_image.py` — imagem por IA (Together / FLUX.2).
- `generate_voice.py` — narração (Google Cloud TTS).
- `compositor.py` — `compor_fundo()` (camada de fundo) + `sobrepor_personagem()` (camada de personagem); `compor_cena()` empilha as duas (compat).
- `pexels.py` — busca de fotos de fundo no Pexels.

## Artefatos escritos em `output/<tipo>/<timestamp>/` (gitignored)

`roteiro.txt`, `prompts.txt` (fundo ia) ou `cenas.txt` (fundo pexels),
`emocoes.txt` (só no fundo por IA + personagem), `images/imagem_N.png`,
`audio/frase_N.mp3`, `legendas.srt` (se ligado), `video_final.mp4` e `sidecar.json`.

Runners: `python -m geracao.pipeline`, `python -m geracao.generate_script`, etc.
