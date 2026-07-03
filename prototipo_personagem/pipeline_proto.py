"""Protótipo de pipeline COMPLETO: roteiro -> narração -> cena (fundo Pexels +
personagem por emoção) -> vídeo vertical (Shorts, 1080x1920).

Diferenças para o pipeline oficial (`scripts/pipeline.py`):
- Não gera imagens por IA. Cada cena é uma FOTO do Pexels (fundo) com o PNG do
  personagem por cima, escolhido pela EMOÇÃO que o modelo definiu para a frase.
- Formato retrato (Shorts), não paisagem.

Para você rodar, só precisa de duas coisas:
1. Os PNGs do personagem em `prototipo_personagem/personagens/` (veja o README).
2. A variável PEXELS_API_KEY no `.env` (chave gratuita em pexels.com/api).
   Sem a chave, ele ainda roda, mas com fundos de placeholder.

Uso:  python -m prototipo_personagem.pipeline_proto
"""

from datetime import datetime
from pathlib import Path

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

from config.sistema import sistema
from config.tipos import carregar_tipo
from scripts.generate_voice import gerar_narracao

from prototipo_personagem import pexels
from prototipo_personagem.compositor import compor_cena
from prototipo_personagem.gerar_cena import gerar_cenas

BASE = Path(__file__).parent
PASTA_SAIDA = BASE / "saida"


def gerar_video_proto(tema: str, tipo_id: str = "cetico_pratico") -> Path:
    tipo = carregar_tipo(tipo_id)

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = PASTA_SAIDA / f"video_{carimbo}"
    pasta_audio = base / "audio"
    pasta_frames = base / "frames"
    for pasta in (base, pasta_audio, pasta_frames):
        pasta.mkdir(parents=True, exist_ok=True)

    # Etapa 1: roteiro + emoção/busca por frase
    print("Gerando roteiro e definindo emoção + busca por frase...")
    cenas = gerar_cenas(f"Gere um roteiro sobre {tema}", tipo.config, tipo.assets_dir)
    (base / "roteiro.txt").write_text(
        "\n".join(f"[{e}] ({b}) {frase}" for _, frase, e, b in cenas), encoding="utf-8"
    )
    print(f"  {len(cenas)} frases.")
    if not pexels.tem_chave():
        print("  AVISO: PEXELS_API_KEY não configurada — usando fundos de placeholder.")

    # Etapa 2: narração (Google TTS), uma por frase
    print("\nGerando narrações...")
    for indice, frase, _, _ in cenas:
        gerar_narracao(frase, pasta_audio / f"frase_{indice}.mp3", tipo.config)
        print(f"  Narração {indice}/{len(cenas)} gerada.")

    # Etapa 3: cenas (fundo Pexels + personagem por emoção)
    print("\nMontando cenas (fundo + personagem)...")
    usados: dict[str, int] = {}  # varia o fundo quando o mesmo termo se repete
    for indice, _, emocao, busca in cenas:
        i_fundo = usados.get(busca, 0)
        usados[busca] = i_fundo + 1
        fundo_bytes = pexels.buscar_imagem(busca, indice=i_fundo)
        quadro = compor_cena(fundo_bytes, emocao, indice_fundo=indice)
        quadro.save(pasta_frames / f"cena_{indice}.png")
        origem = "pexels" if fundo_bytes else "placeholder"
        print(f"  Cena {indice}/{len(cenas)} [{emocao}] fundo={origem} ({busca})")

    # Etapa 4: montagem do vídeo vertical
    print("\nMontando o vídeo final...")
    clipes = []
    for indice, _, _, _ in cenas:
        audio = AudioFileClip(str(pasta_audio / f"frase_{indice}.mp3"))
        clipe = (
            ImageClip(str(pasta_frames / f"cena_{indice}.png"))
            .with_duration(audio.duration)
            .with_audio(audio)
        )
        clipes.append(clipe)

    video_final = concatenate_videoclips(clipes, method="compose")
    caminho_video = base / "video_final.mp4"
    video_final.write_videofile(
        str(caminho_video),
        fps=sistema.get("video.fps"),
        codec=sistema.get("video.codec"),
        audio_codec=sistema.get("video.audio_codec"),
    )

    print(f"\nVídeo gerado: {caminho_video}")
    return caminho_video


if __name__ == "__main__":
    gerar_video_proto(tema="dicas de produtividade para estudantes")
