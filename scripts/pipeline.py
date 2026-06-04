from pathlib import Path
from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

from scripts.generate_script import gerar_roteiro
from scripts.generate_image import gerar_imagem
from scripts.generate_voice import gerar_narracao


def gerar_video(tema: str, output_path: str | Path) -> Path:
    """Executa o pipeline completo de geração de vídeo.

    Args:
        tema: Tema do vídeo a ser gerado.
        output_path: Pasta onde os arquivos intermediários e o vídeo final serão salvos.

    Returns:
        Path do vídeo final gerado.
    """
    base = Path(output_path)
    pasta_audio = base / "audio"
    pasta_imagens = base / "images"

    for pasta in (base, pasta_audio, pasta_imagens):
        pasta.mkdir(parents=True, exist_ok=True)

    # Etapa 1: roteiro
    print("Gerando roteiro...")
    frases_roteiro, prompts_imagens = gerar_roteiro(f"Gere um roteiro sobre {tema}")

    (base / "roteiro.txt").write_text(
        "\n".join(f[1] for f in frases_roteiro), encoding="utf-8"
    )
    print(f"Roteiro salvo em: {base / 'roteiro.txt'}")

    (base / "prompts.txt").write_text(
        "\n".join(p[1] for p in prompts_imagens), encoding="utf-8"
    )
    print(f"Prompts salvos em: {base / 'prompts.txt'}")

    # Etapa 2: narração
    print("\nGerando narrações...")
    for i, (_, frase) in enumerate(frases_roteiro, start=1):
        gerar_narracao(frase, pasta_audio / f"frase_{i}.mp3")
        print(f"  Narração {i}/{len(frases_roteiro)} gerada.")

    # Etapa 3: imagens
    print("\nGerando imagens...")
    referencia = Path("assets/imagem_referencia.png")
    ref_arg = str(referencia) if referencia.exists() else None

    for i, (_, prompt) in enumerate(prompts_imagens, start=1):
        imagem = gerar_imagem(prompt, referencia=ref_arg)
        (pasta_imagens / f"imagem_{i}.png").write_bytes(imagem)
        print(f"  Imagem {i}/{len(prompts_imagens)} gerada.")

    # Etapa 4: montagem
    print("\nMontando o vídeo final...")
    clipes = []

    for i, (_, frase) in enumerate(frases_roteiro, start=1):
        audio = AudioFileClip(str(pasta_audio / f"frase_{i}.mp3"))
        clipe = (
            ImageClip(str(pasta_imagens / f"imagem_{i}.png"))
            .with_duration(audio.duration)
            .with_audio(audio)
        )
        clipes.append(clipe)
        print(f"  Cena {i} montada ({audio.duration:.2f}s)")

    video_final = concatenate_videoclips(clipes, method="compose")
    caminho_video = base / "video_final.mp4"
    video_final.write_videofile(str(caminho_video), fps=24, codec="libx264", audio_codec="aac")

    print(f"\nVídeo gerado com sucesso: {caminho_video}")
    return caminho_video


if __name__ == "__main__":
    gerar_video(
        tema="dicas de produtividade para estudantes",
        output_path="output/teste",
    )