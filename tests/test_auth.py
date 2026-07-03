import pytest

from api.auth import auth_ativo, checar_credenciais, destino_seguro, _caminho_isento


@pytest.fixture
def credenciais(monkeypatch):
    """Configura ADMIN_USER/ADMIN_PASSWORD para os testes de login."""
    monkeypatch.setenv("ADMIN_USER", "davi")
    monkeypatch.setenv("ADMIN_PASSWORD", "segredo123")


@pytest.fixture(autouse=True)
def limpar_admin(monkeypatch):
    """Garante estado limpo — o .env real pode ter ADMIN_USER/PASSWORD."""
    monkeypatch.delenv("ADMIN_USER", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)


def test_auth_ativo_depende_das_duas_chaves(monkeypatch):
    assert auth_ativo() is False
    monkeypatch.setenv("ADMIN_USER", "davi")
    assert auth_ativo() is False  # só uma não basta
    monkeypatch.setenv("ADMIN_PASSWORD", "x")
    assert auth_ativo() is True


def test_credenciais_corretas(credenciais):
    assert checar_credenciais("davi", "segredo123") is True


def test_senha_errada(credenciais):
    assert checar_credenciais("davi", "errada") is False


def test_usuario_errado(credenciais):
    assert checar_credenciais("outro", "segredo123") is False


def test_sem_config_recusa_tudo():
    # sem ADMIN_* no ambiente, nenhuma credencial é aceita
    assert checar_credenciais("davi", "segredo123") is False


def test_destino_seguro_bloqueia_open_redirect():
    assert destino_seguro("/tipos") == "/tipos"
    assert destino_seguro("//evil.com") == "/"       # protocol-relative
    assert destino_seguro("https://evil.com") == "/"  # URL absoluta
    assert destino_seguro(None) == "/"
    assert destino_seguro("") == "/"


def test_caminho_isento():
    assert _caminho_isento("/login") is True
    assert _caminho_isento("/static/css/estilo.css") is True
    assert _caminho_isento("/logout") is True
    assert _caminho_isento("/tipos") is False
    assert _caminho_isento("/configuracoes") is False
