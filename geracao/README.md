# Pilar Geração

Transforma o **tema decidido** pela Descoberta no **artefato de mídia final**: um
`video_final.mp4` + um `sidecar.json` que descreve o vídeo (tema, roteiro, duração,
provedores/custos) e serve de handoff para a Publicação.

A spec de referência é `PILAR_2_GERACAO.md` (raiz), sob dois princípios:
**eficiência** (nunca pagar duas vezes; nunca pagar uma etapa antes de validar a
anterior) e **configurabilidade** (todo provedor/parâmetro/toggle é editável no
painel, na aba "Geração").

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
- `sidecar.py` — escreve/lê o `sidecar.json` (handoff para a Publicação).
- `legendas.py` — SRT + burn-in opcional (default off).
- `pipeline.py` — `gerar_video()`: orquestra os estágios acima.

Provedores plugáveis por papel (`provedores/`):
- `base.py` — registro `(papel, nome) → provedor`; `obter()`, `provedores_de()`.
- `roteiro_groq.py` — roteiro via Groq.
- `visuais_flux.py` — plano (prompts) + render por IA (Together/FLUX), modo "ia".
- `visuais_pexels.py` — plano (emoção+busca) + foto Pexels compondo o personagem, modo "personagem".
- `narracao_google.py` — narração via Google TTS (com override de voz para o fallback).
- *(seam documentado: ElevenLabs entra como `(narracao, "elevenlabs")` sem tocar no pipeline.)*

Chamadas externas concretas embrulhadas pelos provedores:
- `generate_script.py` / `generate_scene.py` — chamadas Groq (roteiro e plano).
- `generate_image.py` — imagem por IA (Together / FLUX.2).
- `generate_voice.py` — narração (Google Cloud TTS).
- `compositor.py` — foto de fundo + PNG do personagem (modo "personagem").
- `pexels.py` — busca de fotos de fundo no Pexels.

## Artefatos escritos em `output/<tipo>/<timestamp>/` (gitignored)

`roteiro.txt`, `prompts.txt` (modo ia) ou `cenas.txt` (modo personagem),
`images/imagem_N.png`, `audio/frase_N.mp3`, `legendas.srt` (se ligado),
`video_final.mp4` e `sidecar.json`.

Runners: `python -m geracao.pipeline`, `python -m geracao.generate_script`, etc.
