import pytest

from config.settings import Config
from geracao import compositor
from geracao.compositor import (
    EMOCAO_PADRAO,
    caminho_personagem,
    compor_cena,
    sobrepor_icone,
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


# --- camada de ícones ------------------------------------------------------


def _icone_png(tmp_path, cor=(255, 0, 0, 255), tamanho=(80, 80)):
    caminho = tmp_path / "icone.png"
    Image.new("RGBA", tamanho, cor).save(caminho, format="PNG")
    return caminho


def test_sobrepor_icone_preserva_tamanho_e_posiciona_no_canto(tmp_path):
    cena = Image.new("RGB", (200, 400), (255, 255, 255))
    icone = _icone_png(tmp_path)
    cfg = {
        "posicao": "superior_direito",
        "tamanho_percentual": 25,  # ic.height = 400*0.25 = 100 (quadrado -> 100x100)
        "margem_lateral": 10,
        "margem_vertical": 20,
    }
    resultado = sobrepor_icone(cena, icone, cfg)

    assert resultado.size == (200, 400)  # não redimensiona o quadro
    # canto superior direito: x=200-10-100=90, y=20 -> centro ~ (140, 70) deve ser vermelho
    assert resultado.getpixel((140, 70))[:3] == (255, 0, 0)
    # canto oposto (inferior esquerdo) intacto = branco
    assert resultado.getpixel((5, 395))[:3] == (255, 255, 255)


def test_sobrepor_icone_inferior_esquerdo(tmp_path):
    cena = Image.new("RGB", (200, 400), (255, 255, 255))
    icone = _icone_png(tmp_path, cor=(0, 0, 255, 255))
    cfg = {
        "posicao": "inferior_esquerdo",
        "tamanho_percentual": 25,
        "margem_lateral": 10,
        "margem_vertical": 20,
    }
    resultado = sobrepor_icone(cena, icone, cfg)
    # x=10, y=400-20-100=280 -> centro ~ (60, 330) deve ser azul
    assert resultado.getpixel((60, 330))[:3] == (0, 0, 255)
