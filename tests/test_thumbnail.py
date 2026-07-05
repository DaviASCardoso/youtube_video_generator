import io
import json

from PIL import Image

from geracao.custo import Ledger
from publicacao import registro, thumbnail


def _png_bytes(cor=(80, 40, 20), tamanho=(400, 300)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buf, format="PNG")
    return buf.getvalue()


def _mock_groq(monkeypatch, texto="CLIQUE AQUI", fundo="a dramatic scene"):
    monkeypatch.setattr(
        "publicacao.thumbnail._chamar_api",
        lambda s, u, c: json.dumps({"texto": texto, "fundo": fundo}),
    )


# --- gerar_thumbnail ------------------------------------------------------


def test_gerar_thumbnail_flux(make_tipo, monkeypatch):
    tipo = make_tipo()  # fonte_fundo default = flux
    _mock_groq(monkeypatch)
    monkeypatch.setattr(
        "publicacao.thumbnail.gerar_imagem", lambda prompt, config, assets: _png_bytes()
    )
    led = Ledger()
    img, dados = thumbnail.gerar_thumbnail(
        {"tema": "tema", "roteiro": "roteiro"}, tipo.config, tipo.assets_dir, ledger=led
    )
    assert img.size == (thumbnail.LARGURA, thumbnail.ALTURA)
    assert dados == {"texto": "CLIQUE AQUI", "fundo": "a dramatic scene"}
    assert led.provedores()["thumbnail_texto"] == "groq"
    assert led.provedores()["thumbnail_fundo"] == "flux"


def test_gerar_thumbnail_pexels(make_tipo, monkeypatch):
    tipo = make_tipo(config_extra={"publicacao": {"thumbnail": {"fonte_fundo": "pexels"}}})
    _mock_groq(monkeypatch)
    monkeypatch.setattr(
        "publicacao.thumbnail.pexels.buscar_imagem",
        lambda termo, orientacao, indice: _png_bytes(),
    )
    led = Ledger()
    img, _ = thumbnail.gerar_thumbnail({"tema": "t", "roteiro": "r"}, tipo.config, tipo.assets_dir, ledger=led)
    assert img.size == (thumbnail.LARGURA, thumbnail.ALTURA)
    assert led.provedores()["thumbnail_fundo"] == "pexels"


def test_pexels_sem_resultado_cai_para_placeholder(make_tipo, monkeypatch):
    tipo = make_tipo(config_extra={"publicacao": {"thumbnail": {"fonte_fundo": "pexels"}}})
    _mock_groq(monkeypatch)
    monkeypatch.setattr(
        "publicacao.thumbnail.pexels.buscar_imagem", lambda termo, orientacao, indice: None
    )
    led = Ledger()
    img, _ = thumbnail.gerar_thumbnail({"tema": "t", "roteiro": "r"}, tipo.config, tipo.assets_dir, ledger=led)
    assert img.size == (thumbnail.LARGURA, thumbnail.ALTURA)
    assert led.provedores()["thumbnail_fundo"] == "placeholder"


def test_flux_falha_cai_para_placeholder(make_tipo, monkeypatch):
    tipo = make_tipo()
    _mock_groq(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("together fora do ar")

    monkeypatch.setattr("publicacao.thumbnail.gerar_imagem", _boom)
    led = Ledger()
    img, _ = thumbnail.gerar_thumbnail({"tema": "t", "roteiro": "r"}, tipo.config, tipo.assets_dir, ledger=led)
    assert img.size == (thumbnail.LARGURA, thumbnail.ALTURA)
    assert led.provedores()["thumbnail_fundo"] == "placeholder"


def test_groq_falha_usa_tema_como_texto(make_tipo, monkeypatch):
    tipo = make_tipo()

    def _boom(*a, **k):
        raise RuntimeError("groq fora do ar")

    monkeypatch.setattr("publicacao.thumbnail._chamar_api", _boom)
    monkeypatch.setattr("publicacao.thumbnail.gerar_imagem", lambda p, c, a: _png_bytes())
    _, dados = thumbnail.gerar_thumbnail({"tema": "meu tema", "roteiro": "r"}, tipo.config, tipo.assets_dir)
    assert dados["texto"] == "meu tema"  # degradou para o tema


# --- obter_thumbnail (toggle + checkpoint) --------------------------------


def test_obter_thumbnail_desligada_devolve_none(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo()  # thumbnail.ativo default = false

    def _explode(*a, **k):
        raise AssertionError("não deveria chamar nada com a thumb desligada")

    monkeypatch.setattr("publicacao.thumbnail._chamar_api", _explode)
    assert thumbnail.obter_thumbnail(tmp_path, tipo.config, tipo.assets_dir) is None


def test_obter_thumbnail_reaproveita_checkpoint(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo(config_extra={"publicacao": {"thumbnail": {"ativo": True}}})
    (tmp_path / "thumbnail.png").write_bytes(_png_bytes())

    def _explode(*a, **k):
        raise AssertionError("não deveria gerar (checkpoint)")

    monkeypatch.setattr("publicacao.thumbnail._chamar_api", _explode)
    caminho = thumbnail.obter_thumbnail(tmp_path, tipo.config, tipo.assets_dir)
    assert caminho == tmp_path / "thumbnail.png"


def test_obter_thumbnail_gera_e_persiste(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo(config_extra={"publicacao": {"thumbnail": {"ativo": True}}})
    (tmp_path / "sidecar.json").write_text(
        json.dumps({"tema": "tema", "roteiro": "roteiro"}), encoding="utf-8"
    )
    _mock_groq(monkeypatch, texto="TÍTULO", fundo="scene")
    monkeypatch.setattr("publicacao.thumbnail.gerar_imagem", lambda p, c, a: _png_bytes())

    caminho = thumbnail.obter_thumbnail(tmp_path, tipo.config, tipo.assets_dir)
    assert caminho == tmp_path / "thumbnail.png"
    assert caminho.exists()
    assert registro.ler(tmp_path)["thumbnail"]["texto"] == "TÍTULO"
