# Pilar Geração

Transforma um tema escolhido no **artefato de mídia final**: roteiro, imagens/cenas, narração e montagem local do `video_final.mp4`.

Módulos:
- `generate_script.py` — roteiro + prompts de imagem (modo "ia"), via Groq.
- `generate_scene.py` — roteiro + emoção/termo de busca por frase (modo "personagem").
- `generate_image.py` — imagem por IA (Together / FLUX.2).
- `generate_voice.py` — narração (Google Cloud TTS).
- `compositor.py` — compõe foto de fundo + PNG do personagem (modo "personagem").
- `pexels.py` — busca fotos de fundo no Pexels.
- `pipeline.py` — `gerar_video()`: orquestra roteiro → cenas → narração → montagem.

Runners: `python -m geracao.pipeline`, `python -m geracao.generate_script`, etc.
Escreve em `output/<tipo>/<timestamp>/` (gitignored).
