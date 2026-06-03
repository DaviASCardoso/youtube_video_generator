from together import Together
from dotenv import load_dotenv
from pathlib import Path
import os
import base64

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

API_KEY = os.getenv("TOGETHER_API_KEY")
MODELO = "black-forest-labs/FLUX.2-dev"
ARQUIVO_STYLE_PROMPT = BASE.parent / "assets" / "style_prompt.txt"

ASPECT_RATIOS = {
    "16:9":  (1344, 768),
    "9:16":  (768, 1344),
    "1:1":   (1024, 1024),
    "4:3":   (1152, 896),
    "3:4":   (896, 1152),
}


def gerar_imagem(prompt: str, aspect_ratio: str, referencia: str | None = None) -> bytes:
    style_prompt = ARQUIVO_STYLE_PROMPT.read_text(encoding="utf-8").strip()
    prompt_final = f"{style_prompt} {prompt}"

    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError(f"Aspect ratio inválido. Opções: {list(ASPECT_RATIOS.keys())}")

    width, height = ASPECT_RATIOS[aspect_ratio]

    cliente = Together(api_key=API_KEY)

    kwargs = dict(
        model=MODELO,
        prompt=prompt_final,
        width=width,
        height=height,
        steps=20,
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
    imagem = gerar_imagem(
        prompt="A focused young woman studying at a wooden desk, warm lamp light",
        aspect_ratio="16:9",
        referencia=BASE.parent / "assets" / "imagem_referencia.png",  # ou caminho pra um arquivo: "ref.jpg"
    )

    Path("output.png").write_bytes(imagem)
    print("Imagem salva em output.png")
