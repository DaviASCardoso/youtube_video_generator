from google.cloud import texttospeech
from pathlib import Path
from dotenv import load_dotenv
import os

BASE = Path(__file__).parent

load_dotenv(BASE.parent / ".env")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    BASE.parent / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
)

# Configurações da voz — edite conforme preferência
IDIOMA = "pt-BR"
VOZ = "pt-BR-Wavenet-B"          # masculina, natural; troque por pt-BR-Wavenet-A para feminina
VELOCIDADE = 1.0                  # 0.25 a 4.0
PITCH = 0.0                       # -20.0 a +20.0


def gerar_narracao(texto: str, caminho_saida: str | Path) -> Path:
    """Gera um arquivo de áudio MP3 a partir de um texto usando o Google Cloud TTS.

    Args:
        texto: Texto a ser narrado.
        caminho_saida: Caminho do arquivo MP3 a ser salvo.

    Returns:
        Path do arquivo gerado.

    Raises:
        ValueError: Se o texto estiver vazio.
        google.api_core.exceptions.GoogleAPIError: Se a chamada à API falhar.
    """
    if not texto.strip():
        raise ValueError("O texto para narração não pode estar vazio.")

    cliente = texttospeech.TextToSpeechClient()

    entrada = texttospeech.SynthesisInput(text=texto)

    voz = texttospeech.VoiceSelectionParams(
        language_code=IDIOMA,
        name=VOZ,
    )

    config_audio = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=VELOCIDADE,
        pitch=PITCH,
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
    arquivo = gerar_narracao(
        texto="Você sabia que a maior parte do nosso dia é consumida por atividades que não contribuem para nossos objetivos?",
        caminho_saida="output/narracao_teste.mp3",
    )
    print(f"Áudio gerado: {arquivo}")