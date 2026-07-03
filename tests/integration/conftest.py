"""Fixtures dos testes de API real (opt-in via --real-api).

O conftest raiz apaga as chaves do ambiente (`limpar_env`) para deixar os testes
mockados determinísticos. Aqui fazemos o contrário: recarregamos as chaves reais
do .env para poder bater nas APIs de verdade. `chaves_reais` depende de
`limpar_env` de propósito, para rodar DEPOIS dele e reinstalar as chaves.
"""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

_RAIZ = Path(__file__).parents[2]
_ENV = dotenv_values(_RAIZ / ".env")


@pytest.fixture(autouse=True)
def chaves_reais(limpar_env, monkeypatch):
    """Reinstala as chaves reais do .env (o limpar_env do conftest raiz as apagou)."""
    for chave, valor in _ENV.items():
        if valor:
            monkeypatch.setenv(chave, valor)

    # generate_voice espera GOOGLE_APPLICATION_CREDENTIALS apontando pro JSON da conta.
    cred = _ENV.get("GOOGLE_CREDENTIALS_FILE")
    if cred:
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(_RAIZ / cred))


@pytest.fixture
def exigir_chave():
    """Devolve um helper que pula o teste se alguma chave necessária faltar."""

    def _exigir(*nomes: str) -> None:
        faltando = [n for n in nomes if not os.getenv(n)]
        if faltando:
            pytest.skip(f"chave(s) ausente(s) no .env: {', '.join(faltando)}")

    return _exigir


@pytest.fixture
def tipo_real():
    """O tipo real 'cetico_pratico' (config/assets válidos para as chamadas reais)."""
    from config.tipos import carregar_tipo

    return carregar_tipo("cetico_pratico")
