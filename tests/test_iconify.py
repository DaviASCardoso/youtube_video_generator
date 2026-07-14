"""Testes do cliente Iconify — tudo offline: rede (`_baixar`) e a rasterização
(`_rasterizar_svg`, que usa cairosvg) são substituídas, então nada toca a internet
nem exige cairosvg instalado."""

import json

from geracao import iconify

SVG_FAKE = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1H0z"/></svg>'
PNG_FAKE = b"\x89PNG\r\n\x1a\nFAKE"


def _busca_json(*nomes):
    return json.dumps({"icons": list(nomes), "total": len(nomes)}).encode("utf-8")


def _mock_rede(monkeypatch, respostas):
    """Substitui `_baixar` por um dispatcher URL->bytes, contando as chamadas."""
    chamadas = []

    def fake(url, timeout):
        chamadas.append(url)
        for fragmento, corpo in respostas.items():
            if fragmento in url:
                return corpo
        return None

    monkeypatch.setattr(iconify, "_baixar", fake)
    return chamadas


def test_buscar_icone_search_fetch_rasteriza(tmp_path, monkeypatch):
    _mock_rede(monkeypatch, {"/search?": _busca_json("mdi:cash"), "/mdi/cash.svg": SVG_FAKE})
    monkeypatch.setattr(iconify, "_rasterizar_svg", lambda svg, tam: PNG_FAKE)

    caminho = iconify.buscar_icone("money", prefixo="mdi", cache_dir=tmp_path / "cache")

    assert caminho is not None and caminho.exists()
    assert caminho.read_bytes() == PNG_FAKE


def test_buscar_icone_copia_para_destino_do_run(tmp_path, monkeypatch):
    _mock_rede(monkeypatch, {"/search?": _busca_json("mdi:clock"), "/mdi/clock.svg": SVG_FAKE})
    monkeypatch.setattr(iconify, "_rasterizar_svg", lambda svg, tam: PNG_FAKE)

    destino = tmp_path / "run" / "icons" / "icone_3.png"
    caminho = iconify.buscar_icone("clock", cache_dir=tmp_path / "cache", destino=destino)

    assert caminho == destino
    assert destino.read_bytes() == PNG_FAKE


def test_buscar_icone_cacheia_por_conceito_e_set(tmp_path, monkeypatch):
    chamadas = _mock_rede(
        monkeypatch, {"/search?": _busca_json("mdi:brain"), "/mdi/brain.svg": SVG_FAKE}
    )
    monkeypatch.setattr(iconify, "_rasterizar_svg", lambda svg, tam: PNG_FAKE)
    cache = tmp_path / "cache"

    p1 = iconify.buscar_icone("brain", cache_dir=cache)
    n_apos_1 = len(chamadas)
    p2 = iconify.buscar_icone("brain", cache_dir=cache)

    assert p1 == p2
    # a segunda vez não bate na rede de novo (search+svg = 2 chamadas só na 1ª)
    assert n_apos_1 == 2 and len(chamadas) == 2


def test_buscar_icone_cor_faz_parte_da_chave(tmp_path, monkeypatch):
    _mock_rede(monkeypatch, {"/search?": _busca_json("mdi:fire"), "/mdi/fire.svg": SVG_FAKE})
    monkeypatch.setattr(iconify, "_rasterizar_svg", lambda svg, tam: PNG_FAKE)
    cache = tmp_path / "cache"

    branco = iconify.buscar_icone("fire", cor="#FFFFFF", cache_dir=cache)
    preto = iconify.buscar_icone("fire", cor="#000000", cache_dir=cache)

    assert branco != preto  # cores diferentes -> arquivos de cache diferentes


def test_conceito_vazio_devolve_none(tmp_path, monkeypatch):
    chamadas = _mock_rede(monkeypatch, {})
    assert iconify.buscar_icone("", cache_dir=tmp_path) is None
    assert iconify.buscar_icone("   ", cache_dir=tmp_path) is None
    assert chamadas == []  # nem chega a buscar


def test_sem_match_devolve_none(tmp_path, monkeypatch):
    _mock_rede(monkeypatch, {"/search?": _busca_json()})  # icons vazio
    assert iconify.buscar_icone("inexistente", cache_dir=tmp_path) is None


def test_falha_de_rede_no_svg_devolve_none(tmp_path, monkeypatch):
    # acha o nome mas o SVG falha (rede) -> None, sem cachear nada
    _mock_rede(monkeypatch, {"/search?": _busca_json("mdi:cash")})  # svg cai no None
    assert iconify.buscar_icone("money", cache_dir=tmp_path) is None
    assert not (tmp_path).glob("*.png") or list((tmp_path).glob("*.png")) == []


def test_falha_de_rasterizacao_devolve_none(tmp_path, monkeypatch):
    _mock_rede(monkeypatch, {"/search?": _busca_json("mdi:cash"), "/mdi/cash.svg": SVG_FAKE})

    def explode(svg, tam):
        raise RuntimeError("cairo boom")

    monkeypatch.setattr(iconify, "_rasterizar_svg", explode)
    assert iconify.buscar_icone("money", cache_dir=tmp_path) is None


def test_slug_normaliza():
    assert iconify._slug("mdi_money growth!") == "mdi_money_growth"
    assert iconify._slug("   ") == "icone"
