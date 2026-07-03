import json
from types import SimpleNamespace

import pytest

from config.settings import Config
from scripts import youtube as y


def _config(youtube_extra=None):
    dados = {
        "youtube": {
            "categoria_id": "22",
            "visibilidade": "private",
            "tags": ["IA", "dev pessoal"],
            "descricao_base": "Inscreva-se no canal!",
            **(youtube_extra or {}),
        }
    }
    import tempfile, os

    caminho = os.path.join(tempfile.mkdtemp(), "config.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    return Config(caminho)


# --- _montar_metadados (pura) ---

def test_montar_metadados_basico():
    corpo = y._montar_metadados("Meu Tema", "O roteiro aqui.", _config())
    assert corpo["snippet"]["title"] == "Meu Tema"
    assert corpo["snippet"]["categoryId"] == "22"
    assert corpo["snippet"]["tags"] == ["IA", "dev pessoal"]
    assert corpo["status"]["privacyStatus"] == "private"
    desc = corpo["snippet"]["description"]
    assert "O roteiro aqui." in desc
    assert "Inscreva-se no canal!" in desc
    assert "#Shorts" in desc
    # tags viram hashtags sem espaço
    assert "#IA" in desc and "#devpessoal" in desc


def test_montar_metadados_corta_titulo_em_100():
    tema = "A" * 250
    corpo = y._montar_metadados(tema, "", _config())
    assert len(corpo["snippet"]["title"]) == y.TITULO_MAX


def test_montar_metadados_visibilidade_mapeada():
    corpo = y._montar_metadados("t", "", _config({"visibilidade": "public"}))
    assert corpo["status"]["privacyStatus"] == "public"


# --- caminhos das credenciais ---

def test_caminho_client_secret_fallback_raiz(make_tipo):
    tipo = make_tipo()
    # sem arquivo por-tipo -> cai na raiz do projeto
    assert y._caminho_client_secret(tipo) == y._CLIENT_SECRET_RAIZ


def test_caminho_client_secret_por_tipo(make_tipo):
    tipo = make_tipo()
    por_tipo = tipo.caminho / "youtube_client_secret.json"
    por_tipo.write_text("{}", encoding="utf-8")
    assert y._caminho_client_secret(tipo) == por_tipo


def test_caminho_token(make_tipo):
    tipo = make_tipo()
    assert y._caminho_token(tipo) == tipo.caminho / "youtube_token.json"


# --- autenticar ---

class _FakeCreds:
    def __init__(self, valid=True, expired=False, refresh_token="rt"):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refreshed = False

    def refresh(self, request):
        self.refreshed = True
        self.valid = True
        self.expired = False

    def to_json(self):
        return '{"token":"novo"}'


def test_autenticar_sem_token_levanta(make_tipo):
    tipo = make_tipo()  # sem youtube_token.json
    with pytest.raises(RuntimeError):
        y.autenticar(tipo)


def test_autenticar_token_valido(make_tipo, monkeypatch):
    tipo = make_tipo()
    y._caminho_token(tipo).write_text("{}", encoding="utf-8")
    fake = _FakeCreds(valid=True)
    monkeypatch.setattr(
        y, "Credentials", SimpleNamespace(from_authorized_user_file=lambda p, s: fake)
    )
    assert y.autenticar(tipo) is fake


def test_autenticar_renova_token_expirado(make_tipo, monkeypatch):
    tipo = make_tipo()
    y._caminho_token(tipo).write_text("{}", encoding="utf-8")
    fake = _FakeCreds(valid=False, expired=True, refresh_token="rt")
    monkeypatch.setattr(
        y, "Credentials", SimpleNamespace(from_authorized_user_file=lambda p, s: fake)
    )
    monkeypatch.setattr(y, "Request", lambda: object())
    creds = y.autenticar(tipo)
    assert creds is fake and fake.refreshed
    # token renovado é regravado no disco
    assert y._caminho_token(tipo).read_text(encoding="utf-8") == '{"token":"novo"}'


# --- publicar_video (cliente mockado) ---

def test_publicar_video(make_tipo, monkeypatch):
    tipo = make_tipo(
        config_extra={
            "youtube": {
                "categoria_id": "22",
                "visibilidade": "private",
                "tags": ["IA"],
                "descricao_base": "",
                "publicar": True,
            }
        }
    )
    capturado = {}

    class _FakeInsert:
        def next_chunk(self):
            return (None, {"id": "VID123"})

    class _FakeVideos:
        def insert(self, part, body, media_body):
            capturado["part"] = part
            capturado["body"] = body
            return _FakeInsert()

    class _FakeService:
        def videos(self):
            return _FakeVideos()

    monkeypatch.setattr(y, "autenticar", lambda tipo, permitir_consentimento=False: object())
    monkeypatch.setattr(y, "build", lambda *a, **k: _FakeService())
    monkeypatch.setattr(y, "MediaFileUpload", lambda *a, **k: object())

    url = y.publicar_video("video_final.mp4", "Meu Tema", tipo, roteiro="olá mundo")

    assert url == "https://youtu.be/VID123"
    assert capturado["part"] == "snippet,status"
    assert capturado["body"]["snippet"]["title"] == "Meu Tema"
    assert capturado["body"]["status"]["privacyStatus"] == "private"
    assert "olá mundo" in capturado["body"]["snippet"]["description"]
