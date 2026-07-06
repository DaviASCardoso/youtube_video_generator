from contextlib import contextmanager

import pytest

from operacoes import notificacoes as n


# --- defaults e mescla -------------------------------------------------------


def test_politica_default_quiet():
    cats = n.NOTIFICACOES_PADRAO["categorias"]
    # master desligado: nada muda para o sistema rodar
    assert n.NOTIFICACOES_PADRAO["ativo"] is False
    # críticas ligadas em high
    for c in n.CATEGORIAS_CRITICAS:
        assert cats[c]["ativo"] is True
        assert cats[c]["prioridade"] == "high"
    # rotina desligadas
    for c in n.CATEGORIAS_ROTINA:
        assert cats[c]["ativo"] is False


def test_enums_sao_validos():
    for c in n.CATEGORIAS:
        assert n.NOTIFICACOES_PADRAO["categorias"][c]["prioridade"] in n.PRIORIDADES


def test_mesclar_none_devolve_default():
    assert n.mesclar_notificacoes(None) == n.NOTIFICACOES_PADRAO
    assert n.mesclar_notificacoes(None) is not n.NOTIFICACOES_PADRAO


def test_mesclar_preenche_e_nao_muta():
    r = n.mesclar_notificacoes({"ativo": True, "categorias": {"etapa": {"ativo": True}}})
    assert r["ativo"] is True
    assert r["categorias"]["etapa"]["ativo"] is True
    assert r["categorias"]["etapa"]["prioridade"] == "low"  # herdado
    assert r["categorias"]["run_falhou"]["ativo"] is True  # herdado
    # não mutou o default
    assert n.NOTIFICACOES_PADRAO["ativo"] is False
    assert n.NOTIFICACOES_PADRAO["categorias"]["etapa"]["ativo"] is False


def test_config_sem_bloco_no_sistema(monkeypatch):
    class _FakeSistema:
        def get(self, chave):
            raise KeyError(chave)

    monkeypatch.setattr(n, "sistema", _FakeSistema())
    assert n.config() == n.NOTIFICACOES_PADRAO


# --- horas de silêncio -------------------------------------------------------


@pytest.mark.parametrize(
    "agora,inicio,fim,esperado",
    [
        ("23:00", "22:00", "08:00", True),   # dentro, cruzando meia-noite
        ("03:00", "22:00", "08:00", True),
        ("12:00", "22:00", "08:00", False),  # fora
        ("08:00", "22:00", "08:00", False),  # fim é exclusivo
        ("13:00", "09:00", "17:00", True),   # janela mesmo-dia
        ("18:00", "09:00", "17:00", False),
        ("10:00", "10:00", "10:00", False),  # janela vazia
    ],
)
def test_dentro_do_silencio(agora, inicio, fim, esperado):
    assert n._dentro_do_silencio(agora, inicio, fim) is esperado


# --- emissão ----------------------------------------------------------------


@contextmanager
def _resp_ok():
    yield object()


def _mock_urlopen(registro):
    def _fake(req, timeout=None):
        registro.append(req)
        return _resp_ok()

    return _fake


def _ligado():
    """Config com master ligado e todas as categorias no default."""
    cfg = n.mesclar_notificacoes({"ativo": True})
    return cfg


def test_emitir_no_op_sem_topico(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.setattr(n, "config", _ligado)
    enviados = []
    monkeypatch.setattr(n.urllib.request, "urlopen", _mock_urlopen(enviados))
    assert n.emitir("run_falhou", "t", "m") is False
    assert enviados == []


def test_emitir_no_op_master_desligado(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "segredo")
    monkeypatch.setattr(n, "config", lambda: n.mesclar_notificacoes(None))  # ativo=False
    enviados = []
    monkeypatch.setattr(n.urllib.request, "urlopen", _mock_urlopen(enviados))
    assert n.emitir("run_falhou", "t", "m") is False
    assert enviados == []


def test_emitir_no_op_categoria_desligada(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "segredo")
    monkeypatch.setattr(n, "config", _ligado)
    enviados = []
    monkeypatch.setattr(n.urllib.request, "urlopen", _mock_urlopen(enviados))
    # video_publicado é rotina, desligada por default
    assert n.emitir("video_publicado", "t", "m") is False
    assert enviados == []


def test_emitir_envia_categoria_ligada(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "segredo")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example.com")
    monkeypatch.setattr(n, "config", _ligado)
    enviados = []
    monkeypatch.setattr(n.urllib.request, "urlopen", _mock_urlopen(enviados))

    assert n.emitir("run_falhou", "Falhou", "corpo") is True
    assert len(enviados) == 1
    req = enviados[0]
    assert req.full_url == "https://ntfy.example.com/segredo"
    assert req.data == "corpo".encode("utf-8")
    assert req.headers["Title"] == "Falhou"
    assert req.headers["Priority"] == "high"


def test_emitir_inclui_token_quando_presente(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "segredo")
    monkeypatch.setenv("NTFY_TOKEN", "tk_abc")
    monkeypatch.setattr(n, "config", _ligado)
    enviados = []
    monkeypatch.setattr(n.urllib.request, "urlopen", _mock_urlopen(enviados))
    n.emitir("credencial", "t", "m")
    assert enviados[0].headers["Authorization"] == "Bearer tk_abc"


def test_silencio_suprime_rotina_mas_nao_critica(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "segredo")
    cfg = n.mesclar_notificacoes(
        {
            "ativo": True,
            "horas_silencio": {"ativo": True, "inicio": "00:00", "fim": "23:59"},
            "categorias": {"video_publicado": {"ativo": True, "prioridade": "default"}},
        }
    )
    monkeypatch.setattr(n, "config", lambda: cfg)
    enviados = []
    monkeypatch.setattr(n.urllib.request, "urlopen", _mock_urlopen(enviados))

    # rotina no silêncio: suprimida
    assert n.emitir("video_publicado", "t", "m") is False
    # crítica fura o silêncio
    assert n.emitir("run_falhou", "t", "m") is True
    assert len(enviados) == 1


def test_emitir_degrada_em_falha_de_rede(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "segredo")
    monkeypatch.setattr(n, "config", _ligado)

    def _boom(req, timeout=None):
        raise OSError("sem rede")

    monkeypatch.setattr(n.urllib.request, "urlopen", _boom)
    # não levanta; devolve False
    assert n.emitir("run_falhou", "t", "m") is False


def test_enviar_teste_ignora_master_mas_precisa_topico(monkeypatch):
    monkeypatch.setattr(n, "config", lambda: n.mesclar_notificacoes(None))  # master off
    enviados = []
    monkeypatch.setattr(n.urllib.request, "urlopen", _mock_urlopen(enviados))

    # sem tópico: não envia
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert n.enviar_teste() is False
    assert enviados == []

    # com tópico: envia mesmo com master off
    monkeypatch.setenv("NTFY_TOPIC", "segredo")
    assert n.enviar_teste() is True
    assert len(enviados) == 1


def test_configurado_reflete_topico(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert n.configurado() is False
    monkeypatch.setenv("NTFY_TOPIC", "x")
    assert n.configurado() is True
    assert n.servidor() == n.SERVIDOR_PADRAO
