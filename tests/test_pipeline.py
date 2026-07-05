import copy
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from config.settings import Config
from geracao import pipeline
from geracao.configuracao import GERACAO_PADRAO
from geracao.custo import GastoDiario
from geracao.pipeline import OrcamentoExcedido, _modo_imagens, gerar_video


def _tipo_com_modo(tmp_path, dados_imagens):
    caminho = tmp_path / "config.json"
    dados = {} if dados_imagens is None else {"imagens": dados_imagens}
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return SimpleNamespace(config=Config(caminho))


def test_modo_imagens_le_config(tmp_path):
    tipo = _tipo_com_modo(tmp_path, {"modo": "personagem"})
    assert _modo_imagens(tipo) == "personagem"


def test_modo_imagens_fallback_ia(tmp_path):
    tipo = _tipo_com_modo(tmp_path, None)  # tipo antigo sem a seção imagens -> "ia"
    assert _modo_imagens(tipo) == "ia"


def test_ler_cenas_parseia_e_indexa_fundo(tmp_path):
    from geracao.pipeline import _ler_cenas

    caminho = tmp_path / "cenas.txt"
    caminho.write_text("[feliz] (office)\n[serio] (office)\n", encoding="utf-8")
    dados = _ler_cenas(caminho)
    assert dados[0] == {"emocao": "feliz", "busca": "office", "i_fundo": 0}
    assert dados[1]["i_fundo"] == 1


# --- fakes de provedor ----------------------------------------------------


class _FakeRoteiro:
    def gerar(self, tema, config, assets_dir, variacao=None, ledger=None):
        if ledger is not None:
            ledger.registrar("roteiro", "groq", 0.0005)
        return [(1, "frase um"), (2, "frase dois")]


class _FakeVisuaisFlux:
    chamou_render = False

    def planejar(self, frases, config, assets_dir, variacao=None, ledger=None):
        if ledger is not None:
            ledger.registrar("plano_visual", "groq", 0.0005)
        return ["prompt a", "prompt b"]

    def renderizar(self, indice, dado, config, assets_dir, variacao=None, ledger=None):
        type(self).chamou_render = True
        if ledger is not None:
            ledger.registrar("visuais", "flux", 0.02)
        return b"IMGBYTES"


class _FakeVisuaisPexels:
    def planejar(self, frases, config, assets_dir, variacao=None, ledger=None):
        return [{"emocao": "neutro", "busca": "x", "i_fundo": 0} for _ in frases]

    def renderizar(self, indice, dado, config, assets_dir, variacao=None, ledger=None):
        if ledger is not None:
            ledger.registrar("visuais", "pexels", 0.0)
        return Image.new("RGB", (8, 8), (10, 20, 30))


class _FakeNarr:
    def narrar(self, texto, caminho, config, voz=None, ledger=None):
        from pathlib import Path

        p = Path(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"0" * 1024)  # acima do mínimo do gate
        return p


class _ProvedorExplode:
    """Qualquer método levanta — usado para provar que o checkpoint não chama provedor."""

    def __getattr__(self, _):
        def _boom(*a, **k):
            raise AssertionError("provedor não deveria ser chamado (checkpoint)")

        return _boom


# --- moviepy falso + isolamento do gasto diário ---------------------------


class _FakeAudio:
    duration = 1.5

    def __init__(self, *a, **k):
        pass


class _FakeImageClip:
    def __init__(self, *a, **k):
        pass

    def with_duration(self, d):
        return self

    def with_audio(self, a):
        return self


class _FakeVideo:
    def __init__(self):
        self.escrito = None

    def write_videofile(self, caminho, **k):
        self.escrito = caminho


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    """moviepy falso + gasto diário isolado + placeholder minúsculo."""
    video = _FakeVideo()
    monkeypatch.setattr(pipeline, "AudioFileClip", _FakeAudio)
    monkeypatch.setattr(pipeline, "ImageClip", _FakeImageClip)
    monkeypatch.setattr(pipeline, "concatenate_videoclips", lambda clipes, **k: video)
    monkeypatch.setattr(pipeline, "gasto_diario", GastoDiario(tmp_path / "custo_diario.json"))
    monkeypatch.setattr(pipeline, "ESPERA_BACKOFF", 0)
    monkeypatch.setattr(
        pipeline, "_fundo_placeholder", lambda i, w, h: Image.new("RGB", (4, 4))
    )
    _FakeVisuaisFlux.chamou_render = False
    return video


def _instalar_provedores(monkeypatch, roteiro=None, visuais=None, narracao=None):
    pedidos = []
    mapa = {
        pipeline.provedores.PAPEL_ROTEIRO: roteiro or _FakeRoteiro(),
        pipeline.provedores.PAPEL_VISUAIS: visuais or _FakeVisuaisFlux(),
        pipeline.provedores.PAPEL_NARRACAO: narracao or _FakeNarr(),
    }

    def _obter(papel, nome):
        pedidos.append((papel, nome))
        return mapa[papel]

    monkeypatch.setattr(pipeline.provedores, "obter", _obter)
    return pedidos


def _tipo_geracao(base=None, **overrides):
    ger = copy.deepcopy(GERACAO_PADRAO)
    for chave, valor in overrides.items():
        ger[chave] = {**ger[chave], **valor} if isinstance(valor, dict) else valor
    return ger


# --- ramos ia vs personagem ----------------------------------------------


def test_gerar_video_ramo_personagem(tmp_path, sistema_temp, make_tipo, ambiente, monkeypatch):
    tipo = make_tipo()  # imagens.modo = "personagem"
    pedidos = _instalar_provedores(monkeypatch, visuais=_FakeVisuaisPexels())

    caminho = gerar_video("tema", tipo, tmp_path / "out")

    assert caminho == tmp_path / "out" / "video_final.mp4"
    assert ambiente.escrito == str(caminho)
    assert (pipeline.provedores.PAPEL_VISUAIS, "pexels") in pedidos
    assert (tmp_path / "out" / "cenas.txt").exists()
    assert (tmp_path / "out" / "sidecar.json").exists()


def test_gerar_video_ramo_ia(tmp_path, sistema_temp, make_tipo, ambiente, monkeypatch):
    tipo = make_tipo(config_extra={"imagens": {"modo": "ia"}})
    pedidos = _instalar_provedores(monkeypatch, visuais=_FakeVisuaisFlux())

    gerar_video("tema", tipo, tmp_path / "out")

    assert (pipeline.provedores.PAPEL_VISUAIS, "flux") in pedidos
    assert (tmp_path / "out" / "prompts.txt").exists()


def test_sidecar_registra_provedores_e_custo(tmp_path, sistema_temp, make_tipo, ambiente, monkeypatch):
    tipo = make_tipo(config_extra={"imagens": {"modo": "ia"}})
    _instalar_provedores(monkeypatch, visuais=_FakeVisuaisFlux())

    gerar_video("meu tema", tipo, tmp_path / "out")

    sc = json.loads((tmp_path / "out" / "sidecar.json").read_text(encoding="utf-8"))
    assert sc["tema"] == "meu tema"
    assert sc["n_cenas"] == 2
    assert sc["provedores"]["visuais"] == "flux"
    assert sc["custo_total_usd"] > 0


# --- checkpoint / resumabilidade -----------------------------------------


def test_checkpoint_reaproveita_tudo(tmp_path, sistema_temp, make_tipo, ambiente, monkeypatch):
    tipo = make_tipo(config_extra={"imagens": {"modo": "ia"}})
    base = tmp_path / "out"
    (base / "images").mkdir(parents=True)
    (base / "audio").mkdir(parents=True)
    (base / "roteiro.txt").write_text("frase um\nfrase dois", encoding="utf-8")
    (base / "prompts.txt").write_text("prompt a\nprompt b", encoding="utf-8")
    for i in (1, 2):
        (base / "images" / f"imagem_{i}.png").write_bytes(b"x")
        (base / "audio" / f"frase_{i}.mp3").write_bytes(b"0" * 1024)

    # Provedores que explodem se chamados: tudo deve vir do checkpoint.
    _instalar_provedores(
        monkeypatch,
        roteiro=_ProvedorExplode(),
        visuais=_ProvedorExplode(),
        narracao=_ProvedorExplode(),
    )

    caminho = gerar_video("tema", tipo, base)
    assert caminho == base / "video_final.mp4"


# --- orçamento ------------------------------------------------------------


def test_orcamento_parar_interrompe(tmp_path, sistema_temp, make_tipo, ambiente, monkeypatch):
    ger = _tipo_geracao(orcamento={"por_video_usd": 0.001, "por_dia_usd": 0.0, "acao": "parar"})
    tipo = make_tipo(config_extra={"imagens": {"modo": "ia"}, "geracao": ger})
    _instalar_provedores(monkeypatch, visuais=_FakeVisuaisFlux())

    with pytest.raises(OrcamentoExcedido):
        gerar_video("tema", tipo, tmp_path / "out")


def test_orcamento_degradar_usa_placeholder(tmp_path, sistema_temp, make_tipo, ambiente, monkeypatch):
    ger = _tipo_geracao(orcamento={"por_video_usd": 0.001, "por_dia_usd": 0.0, "acao": "degradar"})
    tipo = make_tipo(config_extra={"imagens": {"modo": "ia"}, "geracao": ger})
    led = pipeline.Ledger()
    _instalar_provedores(monkeypatch, visuais=_FakeVisuaisFlux())

    gerar_video("tema", tipo, tmp_path / "out", ledger=led)

    assert _FakeVisuaisFlux.chamou_render is False  # não pagou o flux
    assert led.provedores()["visuais"] == "placeholder"


# --- degradação por falha -------------------------------------------------


def test_visual_falha_cai_para_placeholder(tmp_path, sistema_temp, make_tipo, ambiente, monkeypatch):
    class _VisualQuebra(_FakeVisuaisFlux):
        def renderizar(self, *a, **k):
            raise RuntimeError("provedor fora do ar")

    tipo = make_tipo(config_extra={"imagens": {"modo": "ia"}})
    led = pipeline.Ledger()
    _instalar_provedores(monkeypatch, visuais=_VisualQuebra())

    caminho = gerar_video("tema", tipo, tmp_path / "out", ledger=led)

    assert caminho == tmp_path / "out" / "video_final.mp4"
    assert led.provedores()["visuais"] == "placeholder"


def test_narracao_cai_para_voz_secundaria(tmp_path, sistema_temp, make_tipo, ambiente, monkeypatch):
    ger = _tipo_geracao(narracao={"provedor": "google", "voz_secundaria": "voz_b"})
    tipo = make_tipo(config_extra={"imagens": {"modo": "ia"}, "geracao": ger})

    class _NarrPrimariaQuebra:
        def narrar(self, texto, caminho, config, voz=None, ledger=None):
            from pathlib import Path

            if voz is None:
                raise RuntimeError("voz principal falhou")
            p = Path(caminho)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"0" * 1024)
            return p

    _instalar_provedores(monkeypatch, visuais=_FakeVisuaisFlux(), narracao=_NarrPrimariaQuebra())

    caminho = gerar_video("tema", tipo, tmp_path / "out")
    assert caminho == tmp_path / "out" / "video_final.mp4"
