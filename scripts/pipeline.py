from pathlib import Path
from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

from config.tipos import TipoVideo
from config.sistema import sistema
from scripts import pexels
from scripts.compositor import compor_cena, validar_personagens
from scripts.generate_scene import gerar_cenas
from scripts.generate_script import gerar_roteiro
from scripts.generate_image import gerar_imagem
from scripts.generate_voice import gerar_narracao


def _modo_imagens(tipo: TipoVideo) -> str:
    """Modo de geração das cenas: "ia" (Together) ou "personagem" (Pexels + PNG).

    Tipos antigos, sem a seção imagens no config.json, caem no modo "ia" —
    o comportamento original.
    """
    try:
        return tipo.config.get("imagens.modo")
    except KeyError:
        return "ia"


def _gerar_cenas_ia(
    tema: str, tipo: TipoVideo, base: Path, pasta_imagens: Path
) -> list[tuple[int, str]]:
    """Modo original: roteiro -> prompts de imagem -> imagens por IA (Together)."""
    print("Gerando roteiro...")
    frases_roteiro, prompts_imagens = gerar_roteiro(
        f"Gere um roteiro sobre {tema}", tipo.config, tipo.assets_dir
    )

    (base / "roteiro.txt").write_text(
        "\n".join(f[1] for f in frases_roteiro), encoding="utf-8"
    )
    print(f"Roteiro salvo em: {base / 'roteiro.txt'}")

    (base / "prompts.txt").write_text(
        "\n".join(p[1] for p in prompts_imagens), encoding="utf-8"
    )
    print(f"Prompts salvos em: {base / 'prompts.txt'}")

    print("\nGerando imagens...")
    referencia = tipo.assets_dir / "imagem_referencia.png"
    ref_arg = str(referencia) if referencia.exists() else None

    for i, (_, prompt) in enumerate(prompts_imagens, start=1):
        imagem = gerar_imagem(prompt, tipo.config, tipo.assets_dir, referencia=ref_arg)
        (pasta_imagens / f"imagem_{i}.png").write_bytes(imagem)
        print(f"  Imagem {i}/{len(prompts_imagens)} gerada.")

    return frases_roteiro


def _gerar_cenas_personagem(
    tema: str, tipo: TipoVideo, base: Path, pasta_imagens: Path
) -> list[tuple[int, str]]:
    """Modo "personagem": roteiro -> emoção + busca por frase -> foto do Pexels
    de fundo com o PNG do personagem por cima."""
    validar_personagens(tipo.assets_dir)

    print("Gerando roteiro e definindo emoção + busca por frase...")
    cenas = gerar_cenas(f"Gere um roteiro sobre {tema}", tipo.config, tipo.assets_dir)

    (base / "roteiro.txt").write_text(
        "\n".join(frase for _, frase, _, _ in cenas), encoding="utf-8"
    )
    print(f"Roteiro salvo em: {base / 'roteiro.txt'}")

    (base / "cenas.txt").write_text(
        "\n".join(f"[{emocao}] ({busca})" for _, _, emocao, busca in cenas),
        encoding="utf-8",
    )
    print(f"Cenas (emoção + busca) salvas em: {base / 'cenas.txt'}")

    if not pexels.tem_chave():
        print("AVISO: PEXELS_API_KEY não configurada — usando fundos de placeholder.")

    orientacao = (
        "portrait"
        if tipo.config.get("imagens.altura") > tipo.config.get("imagens.largura")
        else "landscape"
    )

    print("\nMontando cenas (fundo + personagem)...")
    usados: dict[str, int] = {}  # varia o fundo quando o mesmo termo se repete
    for indice, _, emocao, busca in cenas:
        i_fundo = usados.get(busca, 0)
        usados[busca] = i_fundo + 1
        fundo_bytes = pexels.buscar_imagem(busca, orientacao=orientacao, indice=i_fundo)
        quadro = compor_cena(fundo_bytes, emocao, tipo.config, tipo.assets_dir, indice=indice)
        quadro.save(pasta_imagens / f"imagem_{indice}.png")
        origem = "pexels" if fundo_bytes else "placeholder"
        print(f"  Cena {indice}/{len(cenas)} [{emocao}] fundo={origem} ({busca})")

    return [(indice, frase) for indice, frase, _, _ in cenas]


def gerar_video(tema: str, tipo: TipoVideo, output_path: str | Path) -> Path:
    """Executa o pipeline completo de geração de vídeo.

    Args:
        tema: Tema do vídeo a ser gerado.
        tipo: Tipo de vídeo (configuração, prompts e assets) a usar na geração.
        output_path: Pasta onde os arquivos intermediários e o vídeo final serão salvos.

    Returns:
        Path do vídeo final gerado.
    """
    base = Path(output_path)
    pasta_audio = base / "audio"
    pasta_imagens = base / "images"

    for pasta in (base, pasta_audio, pasta_imagens):
        pasta.mkdir(parents=True, exist_ok=True)

    # Etapas 1 e 2: roteiro + imagens, conforme o modo do tipo
    if _modo_imagens(tipo) == "personagem":
        frases_roteiro = _gerar_cenas_personagem(tema, tipo, base, pasta_imagens)
    else:
        frases_roteiro = _gerar_cenas_ia(tema, tipo, base, pasta_imagens)

    # Etapa 3: narração
    print("\nGerando narrações...")
    for i, (_, frase) in enumerate(frases_roteiro, start=1):
        gerar_narracao(frase, pasta_audio / f"frase_{i}.mp3", tipo.config)
        print(f"  Narração {i}/{len(frases_roteiro)} gerada.")

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
    video_final.write_videofile(
        str(caminho_video),
        fps=sistema.get("video.fps"),
        codec=sistema.get("video.codec"),
        audio_codec=sistema.get("video.audio_codec"),
    )

    print(f"\nVídeo gerado com sucesso: {caminho_video}")
    return caminho_video


if __name__ == "__main__":
    from config.tipos import carregar_tipo

    gerar_video(
        tema="dicas de produtividade para estudantes",
        tipo=carregar_tipo("cetico_pratico"),
        output_path="output/teste",
    )