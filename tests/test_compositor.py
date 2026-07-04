import pytest

from config.settings import Config
from geracao import compositor
from geracao.compositor import (
    EMOCAO_PADRAO,
    caminho_personagem,
    compor_cena,
    validar_personagens,
    _cobrir,
)
from PIL import Image
import io


_CONFIG = {
    "imagens": {
        "largura": 200,
        "altura": 400,
        "personagem": {
            "posicao": "inferior_esquerdo",
            "altura_percentual": 50,
            "margem_lateral": 10,
            "margem_vertical": 20,
        },
    }
}


def _config(tmp_path, dados=_CONFIG):
    import json

    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return Config(caminho)


def _png_bytes(cor=(200, 100, 50), tamanho=(300, 500)):
    buf = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buf, format="PNG")
    return buf.getvalue()


def test_validar_personagens_sem_neutro_levanta(tmp_path):
    with pytest.raises(FileNotFoundError):
        validar_personagens(tmp_path)


def test_validar_personagens_com_neutro_ok(tmp_path, make_png):
    make_png(caminho_personagem(tmp_path, EMOCAO_PADRAO))
    validar_personagens(tmp_path)  # não deve levantar


def test_compor_cena_tamanho_do_canvas(tmp_path, make_png):
    make_png(caminho_personagem(tmp_path, EMOCAO_PADRAO))
    cena = compor_cena(_png_bytes(), "neutro", _config(tmp_path), tmp_path, indice=0)
    assert cena.size == (200, 400)


def test_compor_cena_sem_fundo_usa_placeholder(tmp_path, make_png):
    make_png(caminho_personagem(tmp_path, EMOCAO_PADRAO))
    # fundo None -> gradiente de placeholder, não deve quebrar
    cena = compor_cena(None, "neutro", _config(tmp_path), tmp_path, indice=1)
    assert cena.size == (200, 400)


def test_compor_cena_emocao_desconhecida_usa_neutro(tmp_path, make_png):
    # só existe o neutro; emoção inexistente deve cair no fallback sem erro
    make_png(caminho_personagem(tmp_path, EMOCAO_PADRAO), cor=(0, 255, 0, 255))
    cena = compor_cena(_png_bytes(), "emocao_que_nao_existe", _config(tmp_path), tmp_path)
    assert cena.size == (200, 400)


def test_compor_cena_emocao_valida_sem_png_usa_neutro(tmp_path, make_png):
    # "feliz" é uma emoção válida mas sem PNG próprio -> cai no neutro
    make_png(caminho_personagem(tmp_path, EMOCAO_PADRAO))
    cena = compor_cena(_png_bytes(), "feliz", _config(tmp_path), tmp_path)
    assert cena.size == (200, 400)


def test_cobrir_preenche_quadro_exato():
    origem = Image.new("RGB", (100, 100), (10, 20, 30))
    coberto = _cobrir(origem, 200, 400)
    assert coberto.size == (200, 400)
