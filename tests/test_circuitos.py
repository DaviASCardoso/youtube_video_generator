import pytest

from operacoes import resiliencia as R
from operacoes.circuitos import ABERTO, FECHADO, MEIO_ABERTO, RegistroCircuitos


@pytest.fixture
def reg(tmp_path):
    return RegistroCircuitos(tmp_path / "circuitos.json")


def _pol(limiar=3, cooldown=300, janela=3600):
    return R.PoliticaFalhas({"circuito": {"limiar_falhas": limiar, "cooldown_seg": cooldown, "janela_saude_seg": janela}})


def test_fechado_por_padrao(reg):
    assert reg.estado("flux", _pol()) == FECHADO


def test_abre_apos_n_falhas(reg):
    pol = _pol(limiar=3, cooldown=300)
    for _ in range(2):
        reg.registrar_falha("flux", agora=1000)
    assert reg.estado("flux", pol, agora=1000) == FECHADO  # ainda abaixo do limiar
    reg.registrar_falha("flux", agora=1000)  # 3ª
    assert reg.estado("flux", pol, agora=1000) == ABERTO


def test_cooldown_vira_meio_aberto(reg):
    pol = _pol(limiar=2, cooldown=300)
    reg.registrar_falha("flux", agora=1000)
    reg.registrar_falha("flux", agora=1000)
    assert reg.estado("flux", pol, agora=1100) == ABERTO           # dentro do cooldown
    assert reg.estado("flux", pol, agora=1000 + 300) == MEIO_ABERTO  # cooldown exato passou
    assert reg.estado("flux", pol, agora=2000) == MEIO_ABERTO


def test_sucesso_fecha_o_circuito(reg):
    pol = _pol(limiar=2)
    reg.registrar_falha("flux", agora=1000)
    reg.registrar_falha("flux", agora=1000)
    assert reg.estado("flux", pol, agora=1000) == ABERTO
    reg.registrar_sucesso("flux")
    assert reg.estado("flux", pol, agora=1000) == FECHADO


def test_probe_falho_reabre(reg):
    pol = _pol(limiar=2, cooldown=300)
    reg.registrar_falha("flux", agora=1000)
    reg.registrar_falha("flux", agora=1000)
    # cooldown passa -> meio_aberto; o probe falha (registra falha em 1400)
    assert reg.estado("flux", pol, agora=1400) == MEIO_ABERTO
    reg.registrar_falha("flux", agora=1400)
    assert reg.estado("flux", pol, agora=1400) == ABERTO         # reabriu
    assert reg.estado("flux", pol, agora=1400 + 300) == MEIO_ABERTO


def test_falhas_recentes_na_janela(reg):
    reg.registrar_falha("flux", agora=1000)
    reg.registrar_falha("flux", agora=2000)
    reg.registrar_falha("flux", agora=5000)
    # janela de 3600s a partir de 5000 -> corte 1400: pega 2000 e 5000
    assert reg.falhas_recentes("flux", 3600, agora=5000) == 2
    assert reg.falhas_recentes("flux", 100000, agora=5000) == 3


def test_isolado_por_provedor(reg):
    pol = _pol(limiar=1)
    reg.registrar_falha("flux", agora=1000)
    assert reg.estado("flux", pol, agora=1000) == ABERTO
    assert reg.estado("google", pol, agora=1000) == FECHADO


def test_persistido_entre_instancias(tmp_path):
    caminho = tmp_path / "circuitos.json"
    RegistroCircuitos(caminho).registrar_falha("flux", agora=1000)
    RegistroCircuitos(caminho).registrar_falha("flux", agora=1000)
    # uma nova instância (== restart) enxerga o estado gravado
    assert RegistroCircuitos(caminho).estado("flux", _pol(limiar=2), agora=1000) == ABERTO


def test_limpar(reg):
    pol = _pol(limiar=1)
    reg.registrar_falha("flux", agora=1000)
    reg.limpar("flux")
    assert reg.estado("flux", pol, agora=1000) == FECHADO
