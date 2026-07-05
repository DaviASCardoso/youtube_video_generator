import pytest

from publicacao.destinos import base
from publicacao.destinos.youtube import DestinoYoutube


def test_registro_obter_e_disponiveis():
    assert isinstance(base.obter("youtube"), DestinoYoutube)
    assert "youtube" in base.disponiveis()


def test_obter_desconhecido():
    with pytest.raises(KeyError):
        base.obter("tiktok")


_METADADOS = {"titulo": "T", "descricao": "D", "tags": ["a"]}
_OPCOES = {"privacidade": "public", "categoria_id": "22", "tags_base": [], "descricao_base": ""}


def test_publicar_imediato(make_tipo, monkeypatch):
    tipo = make_tipo()
    chamadas = {}
    monkeypatch.setattr("publicacao.youtube.subir_video", lambda t, v, corpo: chamadas.__setitem__("corpo", corpo) or "VID1")
    monkeypatch.setattr(
        "publicacao.youtube.definir_thumbnail",
        lambda *a, **k: chamadas.__setitem__("thumb", True),
    )

    res = DestinoYoutube().publicar("v.mp4", _METADADOS, None, _OPCOES, tipo)

    assert res["id"] == "VID1"
    assert res["url"] == "https://youtu.be/VID1"
    assert res["quota"] == 1600
    assert res["privacidade"] == "public"
    assert "thumb" not in chamadas  # sem thumb_path -> não chama thumbnails.set


def test_publicar_define_thumbnail_quando_ha_caminho(make_tipo, monkeypatch):
    tipo = make_tipo()
    chamadas = {}
    monkeypatch.setattr("publicacao.youtube.subir_video", lambda t, v, corpo: "VID2")
    monkeypatch.setattr(
        "publicacao.youtube.definir_thumbnail", lambda t, vid, p: chamadas.setdefault("thumb", (vid, p))
    )
    DestinoYoutube().publicar("v.mp4", _METADADOS, "thumb.png", _OPCOES, tipo)
    assert chamadas["thumb"] == ("VID2", "thumb.png")


def test_publicar_thumbnail_falha_nao_derruba(make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr("publicacao.youtube.subir_video", lambda t, v, corpo: "VID3")

    def _boom(*a, **k):
        raise RuntimeError("thumb rejeitada")

    monkeypatch.setattr("publicacao.youtube.definir_thumbnail", _boom)
    res = DestinoYoutube().publicar("v.mp4", _METADADOS, "thumb.png", _OPCOES, tipo)
    assert res["id"] == "VID3"  # publicou apesar da thumb falhar


def test_publicar_agendado(make_tipo, monkeypatch):
    tipo = make_tipo()
    chamadas = {}
    monkeypatch.setattr("publicacao.youtube.subir_video", lambda t, v, corpo: chamadas.__setitem__("corpo", corpo) or "VID4")
    opcoes = {**_OPCOES, "publish_at": "2026-07-06T18:00:00Z"}
    res = DestinoYoutube().publicar("v.mp4", _METADADOS, None, opcoes, tipo)
    assert chamadas["corpo"]["status"]["publishAt"] == "2026-07-06T18:00:00Z"
    assert res["privacidade"] == "private"
    assert res["agendado_para"] == "2026-07-06T18:00:00Z"


def test_checar_credencial_delega(make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr("publicacao.youtube.checar_credencial", lambda t: {"status": "valido", "detalhe": ""})
    assert DestinoYoutube().checar_credencial(tipo)["status"] == "valido"
