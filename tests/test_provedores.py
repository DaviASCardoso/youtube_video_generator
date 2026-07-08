import io
import json

import pytest
from PIL import Image

from geracao.custo import (
    CUSTO_FLUX_IMAGEM,
    CUSTO_GROQ_CHAMADA,
    Ledger,
    custo_tts,
)
from geracao.provedores import base
from geracao.provedores.narracao_google import NarracaoGoogle
from geracao.provedores.roteiro_groq import RoteiroGroq
from geracao.provedores.visuais_flux import VisuaisFlux
from geracao.provedores.visuais_pexels import VisuaisPexels


def _png_bytes(cor=(120, 60, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), cor).save(buf, format="PNG")
    return buf.getvalue()


# --- registro -------------------------------------------------------------


def test_obter_e_provedores_de():
    assert isinstance(base.obter(base.PAPEL_ROTEIRO, "groq"), RoteiroGroq)
    assert "groq" in base.provedores_de(base.PAPEL_ROTEIRO)
    assert set(base.provedores_de(base.PAPEL_VISUAIS)) >= {"flux", "pexels"}
    assert "google" in base.provedores_de(base.PAPEL_NARRACAO)


def test_obter_desconhecido():
    with pytest.raises(KeyError):
        base.obter(base.PAPEL_ROTEIRO, "inexistente")


def test_provedor_visuais_para_modo():
    assert base.provedor_visuais_para_modo("ia") == "flux"
    assert base.provedor_visuais_para_modo("personagem") == "pexels"


# --- roteiro (Groq) -------------------------------------------------------


def test_roteiro_groq_gera_frases_e_registra_custo(make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(
        "geracao.provedores.roteiro_groq._chamar_api",
        lambda system, user, config: "Primeira frase bem completa aqui. Segunda frase também completa.",
    )
    led = Ledger()
    frases = RoteiroGroq().gerar("produtividade", tipo.config, tipo.assets_dir, ledger=led)

    assert frases and frases[0][0] == 1
    assert all(f[1].strip() for f in frases)
    assert led.total() == CUSTO_GROQ_CHAMADA
    assert led.provedores()["roteiro"] == "groq"


def test_roteiro_groq_aplica_variacao_ao_system_prompt(make_tipo, monkeypatch):
    tipo = make_tipo()
    capturado = {}

    def _fake(system, user, config):
        capturado["system"] = system
        return "Uma frase completa e suficientemente longa aqui."

    monkeypatch.setattr("geracao.provedores.roteiro_groq._chamar_api", _fake)

    from geracao.variacao import Variacao

    var = Variacao({"aberturas": 1.0, "estrutura": 1.0}, semente=1)
    RoteiroGroq().gerar("tema", tipo.config, tipo.assets_dir, variacao=var)
    assert len(capturado["system"]) > len("prompt de teste")  # diretriz anexada


# --- visuais FLUX ---------------------------------------------------------


def test_visuais_flux_planejar(make_tipo, monkeypatch):
    tipo = make_tipo()
    (tipo.assets_dir / "system_prompt_prompt.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        "geracao.provedores.visuais_flux._chamar_api",
        lambda s, u, c: json.dumps(["prompt a", "prompt b"]),
    )
    led = Ledger()
    prompts = VisuaisFlux().planejar(
        [(1, "frase um"), (2, "frase dois")], tipo.config, tipo.assets_dir, ledger=led
    )
    assert prompts == ["prompt a", "prompt b"]
    assert led.total() == CUSTO_GROQ_CHAMADA


def test_visuais_flux_renderizar(make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(
        "geracao.provedores.visuais_flux.gerar_imagem",
        lambda prompt, config, assets, referencia=None: b"IMG",
    )
    led = Ledger()
    out = VisuaisFlux().renderizar(1, "um prompt", tipo.config, tipo.assets_dir, ledger=led)
    assert out == b"IMG"
    assert led.total() == CUSTO_FLUX_IMAGEM
    assert led.provedores()["visuais"] == "flux"


# --- visuais Pexels + personagem -----------------------------------------


def test_visuais_pexels_planejar_normaliza_e_indexa_fundo(make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(
        "geracao.provedores.visuais_pexels._chamar_api",
        lambda s, u, c: json.dumps(
            [
                {"emocao": "feliz", "busca": "office desk"},
                {"emocao": "lixo", "busca": ""},          # normaliza p/ neutro + fallback
                {"emocao": "serio", "busca": "office desk"},  # termo repetido -> i_fundo=1
            ]
        ),
    )
    dados = VisuaisPexels().planejar(
        [(1, "a"), (2, "b"), (3, "c")], tipo.config, tipo.assets_dir
    )
    assert dados[0]["emocao"] == "feliz" and dados[0]["i_fundo"] == 0
    assert dados[1]["emocao"] == "neutro" and dados[1]["busca"]
    assert dados[2]["busca"] == "office desk" and dados[2]["i_fundo"] == 1


def test_visuais_pexels_renderizar_placeholder(make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(
        "geracao.provedores.visuais_pexels.pexels.buscar_imagem",
        lambda termo, orientacao, indice: None,  # sem chave -> placeholder
    )
    led = Ledger()
    quadro = VisuaisPexels().renderizar(
        1, {"emocao": "neutro", "busca": "x", "i_fundo": 0}, tipo.config, tipo.assets_dir, ledger=led
    )
    assert isinstance(quadro, Image.Image)
    assert led.provedores()["visuais"] == "placeholder"


def test_visuais_pexels_renderizar_com_foto(make_tipo, monkeypatch):
    tipo = make_tipo()
    monkeypatch.setattr(
        "geracao.provedores.visuais_pexels.pexels.buscar_imagem",
        lambda termo, orientacao, indice: _png_bytes(),
    )
    led = Ledger()
    quadro = VisuaisPexels().renderizar(
        1, {"emocao": "feliz", "busca": "x", "i_fundo": 0}, tipo.config, tipo.assets_dir, ledger=led
    )
    assert isinstance(quadro, Image.Image)
    assert led.provedores()["visuais"] == "pexels"


def test_visuais_pexels_planejar_nao_exige_personagem(make_tipo, monkeypatch):
    # A camada de fundo (Pexels) é independente do personagem: planejar o fundo
    # não requer PNG de personagem. O fail-fast vive no pipeline, ligado à camada
    # de personagem (não à fonte do fundo).
    tipo = make_tipo(com_personagem=False)
    monkeypatch.setattr(
        "geracao.provedores.visuais_pexels._chamar_api",
        lambda s, u, c: '[{"emocao": "neutro", "busca": "office"}]',
    )
    dados = VisuaisPexels().planejar([(1, "a")], tipo.config, tipo.assets_dir)
    assert dados[0]["busca"] == "office"


# --- narração (Google) ----------------------------------------------------


def test_narracao_google_narra_e_registra_custo(make_tipo, monkeypatch, tmp_path):
    tipo = make_tipo()
    capturado = {}

    def _fake(texto, caminho, config, voz=None):
        capturado["voz"] = voz
        from pathlib import Path

        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"audio")
        return p

    monkeypatch.setattr("geracao.provedores.narracao_google.gerar_narracao", _fake)
    led = Ledger()
    texto = "uma frase de teste"
    NarracaoGoogle().narrar(texto, tmp_path / "f.mp3", tipo.config, voz="voz_sec", ledger=led)

    assert capturado["voz"] == "voz_sec"  # override repassado
    assert abs(led.total() - custo_tts(texto)) < 1e-12
