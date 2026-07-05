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


def _suporta_pitch(voz: str) -> bool:
    """As vozes Chirp/Chirp3-HD não aceitam o parâmetro pitch — a API rejeita a
    chamada. Para elas, o pitch do config é ignorado (a emoção vem do timbre da
    própria voz), em vez de derrubar a execução."""
    return "chirp" not in voz.lower()


def gerar_narracao(
    texto: str, caminho_saida: str | Path, config: Config, voz: str | None = None
) -> Path:
    if not texto.strip():
        raise ValueError("O texto para narração não pode estar vazio.")

    cliente = texttospeech.TextToSpeechClient()

    entrada = texttospeech.SynthesisInput(text=texto)

    # `voz` sobrepõe a voz do config (usado no fallback para a voz secundária).
    nome_voz = voz or config.get("tts.voz")
    voz = texttospeech.VoiceSelectionParams(
        language_code=config.get("tts.idioma"),
        name=nome_voz,
    )

    parametros_audio = dict(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=config.get("tts.velocidade"),
    )
    if _suporta_pitch(nome_voz):
        parametros_audio["pitch"] = config.get("tts.pitch")

    config_audio = texttospeech.AudioConfig(**parametros_audio)

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