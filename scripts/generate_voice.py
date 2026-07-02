from google.cloud import texttospeech
from dotenv import load_dotenv
from pathlib import Path
from config.settings import Config
import os

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    BASE.parent / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
)


def gerar_narracao(texto: str, caminho_saida: str | Path, config: Config) -> Path:
    if not texto.strip():
        raise ValueError("O texto para narração não pode estar vazio.")

    cliente = texttospeech.TextToSpeechClient()

    entrada = texttospeech.SynthesisInput(text=texto)

    voz = texttospeech.VoiceSelectionParams(
        language_code=config.get("tts.idioma"),
        name=config.get("tts.voz"),
    )

    config_audio = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=config.get("tts.velocidade"),
        pitch=config.get("tts.pitch"),
    )

    resposta = cliente.synthesize_speech(
        input=entrada,
        voice=voz,
        audio_config=config_audio,
    )

    saida = Path(caminho_saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_bytes(resposta.audio_content)

    return saida


if __name__ == "__main__":
    from config.tipos import carregar_tipo

    tipo = carregar_tipo("cetico_pratico")
    arquivo = gerar_narracao(
        texto="Você sabia que a maior parte do nosso dia é consumida por atividades que não contribuem para nossos objetivos?",
        caminho_saida="output/narracao_teste.mp3",
        config=tipo.config,
    )
    print(f"Áudio gerado: {arquivo}")