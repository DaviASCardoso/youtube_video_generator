from together import Together
from dotenv import load_dotenv
from pathlib import Path
from config.settings import Config
import os
import base64

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

API_KEY = os.getenv("TOGETHER_API_KEY")

ASPECT_RATIOS = {
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "1:1":  (1024, 1024),
    "4:3":  (1152, 896),
    "3:4":  (896, 1152),
}


def gerar_imagem(
    prompt: str, config: Config, assets_dir: Path, referencia: str | None = None
) -> bytes:
    style_prompt = (assets_dir / "style_prompt.txt").read_text(encoding="utf-8").strip()
    prompt_final = f"{style_prompt} {prompt}"

    aspect_ratio = config.get("together.aspect_ratio")
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError(f"Aspect ratio inválido: '{aspect_ratio}'. Opções: {list(ASPECT_RATIOS.keys())}")

    width, height = ASPECT_RATIOS[aspect_ratio]

    cliente = Together(api_key=API_KEY)

    kwargs = dict(
        model=config.get("together.modelo"),
        prompt=prompt_final,
        width=width,
        height=height,
        steps=config.get("together.steps"),
        response_format="base64",
    )

    if referencia:
        caminho_ref = Path(referencia)
        if not caminho_ref.exists():
            raise FileNotFoundError(f"Imagem de referência não encontrada: {referencia}")
        dados_ref = base64.b64encode(caminho_ref.read_bytes()).decode("utf-8")
        extensao = caminho_ref.suffix.lstrip(".").lower()
        mime = "image/jpeg" if extensao in ("jpg", "jpeg") else f"image/{extensao}"
        kwargs["reference_images"] = [f"data:{mime};base64,{dados_ref}"]

    resposta = cliente.images.generate(**kwargs)
    return base64.b64decode(resposta.data[0].b64_json)


if __name__ == "__main__":
    from config.tipos import carregar_tipo

    tipo = carregar_tipo("cetico_pratico")
    imagem = gerar_imagem(
        "A focused young woman studying at a wooden desk, warm lamp light",
        tipo.config,
        tipo.assets_dir,
    )
    Path("output.png").write_bytes(imagem)
    print("Imagem salva em output.png")