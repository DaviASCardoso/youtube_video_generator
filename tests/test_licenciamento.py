from conformidade.licenciamento import verificar_licenciamento
from conformidade.regras import REGRAS_PADRAO


def test_todos_provedores_licenciados_passa():
    sidecar = {"provedores": {"roteiro": "groq", "visuais": "pexels", "narracao": "google"}}
    r = verificar_licenciamento(sidecar, REGRAS_PADRAO)
    assert r["ok"] is True
    assert r["sem_licenca"] == []


def test_iconify_e_licenciado_por_padrao():
    # ícones do Iconify (set padrão mdi = Apache-2.0, sem atribuição) são licenciados
    sidecar = {"provedores": {"visuais": "flux", "icones": "iconify"}}
    r = verificar_licenciamento(sidecar, REGRAS_PADRAO)
    assert r["ok"] is True
    assert r["sem_licenca"] == []


def test_provedor_desconhecido_bloqueia():
    # 'musica' não está no mapa de licenças → sem licença → bloqueia
    sidecar = {"custos": [
        {"estagio": "narracao", "provedor": "google"},
        {"estagio": "trilha", "provedor": "musica"},
    ]}
    r = verificar_licenciamento(sidecar, REGRAS_PADRAO)
    assert r["ok"] is False
    assert {"estagio": "trilha", "provedor": "musica"} in r["sem_licenca"]


def test_provedor_marcado_false_bloqueia():
    regras = {"licencas": {"flux": True, "duvidoso": False}}
    sidecar = {"provedores": {"visuais": "duvidoso"}}
    r = verificar_licenciamento(sidecar, regras)
    assert r["ok"] is False
    assert r["sem_licenca"][0]["provedor"] == "duvidoso"


def test_custos_pega_mistura_por_cena():
    # provedores coarse só mostra pexels, mas custos revela um ativo sem licença
    sidecar = {
        "provedores": {"visuais": "pexels"},
        "custos": [
            {"estagio": "visuais", "provedor": "pexels"},
            {"estagio": "visuais", "provedor": "banco_pirata"},
        ],
    }
    r = verificar_licenciamento(sidecar, REGRAS_PADRAO)
    assert r["ok"] is False
    assert any(a["provedor"] == "banco_pirata" for a in r["sem_licenca"])


def test_dedup_por_estagio_provedor():
    sidecar = {"custos": [
        {"estagio": "visuais", "provedor": "flux"},
        {"estagio": "visuais", "provedor": "flux"},
    ]}
    r = verificar_licenciamento(sidecar, REGRAS_PADRAO)
    assert r["ok"] is True


def test_sidecar_ausente_passa():
    assert verificar_licenciamento(None, REGRAS_PADRAO) == {"ok": True, "sem_licenca": []}
