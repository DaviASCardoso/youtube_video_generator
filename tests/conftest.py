"""Fixtures e isolamento compartilhados pelos testes.

Princípios:
- Nenhum teste toca nas pastas reais (tipos/, execucoes/, tendencias/) nem no
  config/sistema.json — tudo é redirecionado para tmp_path.
- Nenhuma chamada de API externa é feita — os clientes são mockados nos testes.
- As chaves de API do .env são apagadas do ambiente por padrão, para que os
  ramos tem_chave()/RuntimeError sejam determinísticos.
"""

import json
from pathlib import Path

import pytest
from PIL import Image

from conformidade.configuracao import CONFORMIDADE_PADRAO
from descoberta.configuracao import DESCOBERTA_PADRAO
from feedback.configuracao import FEEDBACK_PADRAO
from geracao.configuracao import GERACAO_PADRAO
from operacoes.configuracao import OPERACAO_PADRAO
from publicacao.configuracao import PUBLICACAO_PADRAO


# --- Testes de API real (opt-in) -------------------------------------------
# Os testes marcados com @pytest.mark.real_api fazem chamadas de verdade às APIs
# externas (gastam cota/dinheiro e precisam de rede + chaves). Ficam de fora do
# `pytest` normal; rode com `pytest --real-api` para incluí-los.


def pytest_addoption(parser):
    parser.addoption(
        "--real-api",
        action="store_true",
        default=False,
        help="também roda os testes que fazem chamadas reais às APIs externas",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_api: chamada real a uma API externa (precisa de --real-api e da chave)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--real-api"):
        return
    pular = pytest.mark.skip(reason="precisa de --real-api (faz chamada real à API)")
    for item in items:
        if "real_api" in item.keywords:
            item.add_marker(pular)

_CHAVES_API = (
    "GROQ_API_KEY",
    "TOGETHER_API_KEY",
    "PEXELS_API_KEY",
    "TRENDS_MCP_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CREDENTIALS_FILE",
    "NTFY_SERVER",
    "NTFY_TOPIC",
    "NTFY_TOKEN",
)


@pytest.fixture(autouse=True)
def limpar_env(monkeypatch):
    """Remove as chaves de API do ambiente antes de cada teste.

    O .env real existe no repo e é carregado no import dos módulos; sem isso,
    testes de 'sem chave' seriam não-determinísticos na máquina do dev.
    """
    for chave in _CHAVES_API:
        monkeypatch.delenv(chave, raising=False)


@pytest.fixture(autouse=True)
def circuito_isolado(tmp_path, monkeypatch):
    """Aponta o store de circuito do motor para um arquivo temporário.

    O singleton `operacoes.circuitos.circuitos` grava em execucoes/circuitos.json;
    sem isso, um teste que exercita falha (retry/failover) escreveria no disco real.
    """
    import operacoes.circuitos as circ_mod
    import operacoes.resiliencia as resil_mod

    store = circ_mod.RegistroCircuitos(tmp_path / "circuitos.json")
    monkeypatch.setattr(resil_mod, "circuitos", store)
    return store


def _png_minimo(caminho: Path, cor=(0, 0, 0, 255), tamanho=(20, 40)) -> Path:
    """Escreve um PNG RGBA minúsculo (para testes do compositor)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", tamanho, cor).save(caminho)
    return caminho


@pytest.fixture
def make_png():
    """Fábrica de PNGs de teste."""
    return _png_minimo


_CONFIG_TIPO_PADRAO = {
    "nome": "Tipo Teste",
    "ativo": True,
    "groq": {"modelo": "m", "temperatura": 0.8, "max_tokens": 100},
    "together": {"modelo": "m", "steps": 10, "aspect_ratio": "9:16"},
    "imagens": {
        "modo": "personagem",
        "largura": 1080,
        "altura": 1920,
        "personagem": {
            "posicao": "inferior_esquerdo",
            "altura_percentual": 62,
            "margem_lateral": 10,
            "margem_vertical": 380,
        },
    },
    "tts": {"idioma": "pt-BR", "voz": "v", "velocidade": 1.0, "pitch": 0.0},
    "pipeline": {"min_chars_por_periodo": 20},
    "agendamento": {"frequencia": "daily", "horario": "06:00", "fuso_horario": "America/Sao_Paulo"},
    "youtube": {
        "categoria_id": "22",
        "visibilidade": "private",
        "tags": [],
        "publicar": False,
        "descricao_base": "",
    },
    "descoberta": DESCOBERTA_PADRAO,
    "geracao": GERACAO_PADRAO,
    "publicacao": PUBLICACAO_PADRAO,
    "feedback": FEEDBACK_PADRAO,
    "operacao": OPERACAO_PADRAO,
    "conformidade": CONFORMIDADE_PADRAO,
}


@pytest.fixture
def tipos_dir(tmp_path, monkeypatch):
    """Redireciona config.tipos._TIPOS_DIR para uma pasta temporária."""
    import config.tipos as tipos_mod

    destino = tmp_path / "tipos"
    destino.mkdir()
    monkeypatch.setattr(tipos_mod, "_TIPOS_DIR", destino)
    return destino


@pytest.fixture
def make_tipo(tipos_dir):
    """Cria um tipo mínimo em disco (config.json + assets + PNG neutro) e o carrega."""
    from config.tipos import carregar_tipo

    def _criar(id_tipo="tipo_teste", ativo=True, config_extra=None, com_personagem=True):
        pasta = tipos_dir / id_tipo
        assets = pasta / "assets"
        assets.mkdir(parents=True)

        config = json.loads(json.dumps(_CONFIG_TIPO_PADRAO))  # deep copy
        config["ativo"] = ativo
        if config_extra:
            config.update(config_extra)
        (pasta / "config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (pasta / "temas.json").write_text("[]", encoding="utf-8")
        for nome in ("system_prompt_script.txt", "system_prompt_cena.txt", "style_prompt.txt"):
            (assets / nome).write_text("prompt de teste", encoding="utf-8")
        if com_personagem:
            _png_minimo(assets / "personagens" / "personagem_neutro.png")

        return carregar_tipo(id_tipo)

    return _criar


@pytest.fixture
def sistema_temp(monkeypatch):
    """Injeta valores conhecidos no singleton config.sistema.sistema, restaurando depois."""
    from config.sistema import sistema

    original = sistema._config
    valores = {
        "execucao": {"max_simultaneo": 1},
        "saida": {"pasta_base": "output"},
        "video": {"fps": 24, "codec": "libx264", "audio_codec": "aac"},
    }
    sistema._config = json.loads(json.dumps(valores))
    yield sistema
    sistema._config = original
