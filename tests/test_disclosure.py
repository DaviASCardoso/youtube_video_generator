from conformidade.disclosure import avaliar_disclosure
from conformidade.regras import REGRAS_PADRAO

REGRAS = REGRAS_PADRAO  # o conteúdo completo de regras (disclosure + marca + licencas)


def test_ia_narracao_mais_visual_realista_exige():
    # cetico_pratico típico: narração google (TTS) + visual pexels (stock realista)
    sidecar = {"provedores": {"narracao": "google", "visuais": "pexels", "roteiro": "groq"}}
    r = avaliar_disclosure(sidecar, REGRAS)
    assert r["requer"] is True
    assert "google" in r["base"] and "pexels" in r["base"]


def test_ia_narracao_mais_flux_exige():
    sidecar = {"provedores": {"narracao": "google", "visuais": "flux"}}
    assert avaliar_disclosure(sidecar, REGRAS)["requer"] is True


def test_custos_como_fonte_fina():
    # provedores coarse aponta placeholder, mas custos revela que houve flux numa cena
    sidecar = {
        "provedores": {"narracao": "google", "visuais": "placeholder"},
        "custos": [
            {"estagio": "visuais", "provedor": "flux"},
            {"estagio": "visuais", "provedor": "placeholder"},
        ],
    }
    assert avaliar_disclosure(sidecar, REGRAS)["requer"] is True


def test_sem_narracao_sintetica_nao_exige():
    sidecar = {"provedores": {"narracao": "humano", "visuais": "pexels"}}
    r = avaliar_disclosure(sidecar, REGRAS)
    assert r["requer"] is False
    assert "sem narração sintética" in r["base"]


def test_sem_visual_qualificado_nao_exige():
    sidecar = {"provedores": {"narracao": "google", "visuais": "placeholder"}}
    r = avaliar_disclosure(sidecar, REGRAS)
    assert r["requer"] is False
    assert "sem visual" in r["base"]


def test_sidecar_ausente_nao_bloqueia():
    r = avaliar_disclosure(None, REGRAS)
    assert r["requer"] is False
    assert "ausente" in r["base"]


def test_respeita_regras_customizadas():
    # regra que trata 'humano' como sintético e apenas 'flux' como visual
    regras = {
        "disclosure": {
            "narracao_sintetica": ["humano"],
            "visual_sintetico_ou_realista": ["flux"],
        }
    }
    assert avaliar_disclosure({"provedores": {"narracao": "humano", "visuais": "flux"}}, regras)["requer"] is True
    assert avaliar_disclosure({"provedores": {"narracao": "google", "visuais": "flux"}}, regras)["requer"] is False
