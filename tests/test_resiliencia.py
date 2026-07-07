import errno

import pytest

from operacoes import resiliencia as R


# --- fakes que imitam a forma dos vários clientes ---------------------------


class _ErroStatus(Exception):
    """Erro com status_code (Groq/Together/openai-style)."""
    def __init__(self, status, msg=""):
        super().__init__(msg or f"status {status}")
        self.status_code = status


class _ErroResp(Exception):
    """Erro com .resp dict (googleapiclient.HttpError-style)."""
    def __init__(self, status, msg=""):
        super().__init__(msg or f"http {status}")
        self.resp = {"status": str(status)}


class _ErroCode(Exception):
    """Erro com .code (urllib.error.HTTPError-style)."""
    def __init__(self, code, msg=""):
        super().__init__(msg or f"code {code}")
        self.code = code


# --- classificação por status ------------------------------------------------


@pytest.mark.parametrize("status,esperado", [
    (500, R.TRANSITORIO), (502, R.TRANSITORIO), (503, R.TRANSITORIO),
    (408, R.TRANSITORIO), (429, R.TRANSITORIO),
    (401, R.AUTH), (403, R.AUTH),
    (400, R.PERMANENTE), (404, R.PERMANENTE), (422, R.PERMANENTE),
])
def test_classifica_por_status_code(status, esperado):
    assert R.classificar(_ErroStatus(status)) == esperado


def test_classifica_por_resp_dict_google():
    assert R.classificar(_ErroResp(500)) == R.TRANSITORIO
    assert R.classificar(_ErroResp(403)) == R.AUTH
    assert R.classificar(_ErroResp(404)) == R.PERMANENTE


def test_classifica_por_code_urllib():
    assert R.classificar(_ErroCode(500)) == R.TRANSITORIO
    assert R.classificar(_ErroCode(401)) == R.AUTH


def test_429_com_quota_vira_quota():
    assert R.classificar(_ErroStatus(429, "Quota exceeded for quota metric")) == R.QUOTA
    assert R.classificar(_ErroStatus(429, "insufficient_quota: out of credits")) == R.QUOTA
    # 429 de rate-limit puro segue transitório (retryável)
    assert R.classificar(_ErroStatus(429, "Rate limit reached, slow down")) == R.TRANSITORIO


# --- classificação por tipo stdlib ------------------------------------------


def test_timeout_e_conexao_sao_transitorios():
    assert R.classificar(TimeoutError("timed out")) == R.TRANSITORIO
    assert R.classificar(ConnectionError("dropped")) == R.TRANSITORIO
    assert R.classificar(ConnectionResetError("reset")) == R.TRANSITORIO


def test_recurso_esgotado():
    assert R.classificar(MemoryError()) == R.RECURSO
    e = OSError("no space left")
    e.errno = errno.ENOSPC
    assert R.classificar(e) == R.RECURSO


def test_validacao_e_permanente():
    assert R.classificar(ValueError("campo inválido")) == R.PERMANENTE
    assert R.classificar(KeyError("faltando")) == R.PERMANENTE


def test_orcamento_excedido_e_quota():
    from geracao.pipeline import OrcamentoExcedido
    assert R.classificar(OrcamentoExcedido("estourou")) == R.QUOTA


# --- classificação por nome/mensagem (sem status) ---------------------------


def test_por_nome_sem_status():
    class AuthenticationError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class RefreshError(Exception):
        pass

    assert R.classificar(AuthenticationError("bad key")) == R.AUTH
    assert R.classificar(APITimeoutError("deadline")) == R.TRANSITORIO
    assert R.classificar(RefreshError("token expired")) == R.AUTH


def test_desconhecido_cai_em_transitorio():
    assert R.classificar(Exception("algo estranho")) == R.TRANSITORIO


# --- retry_after ------------------------------------------------------------


class _ErroHeaders(Exception):
    def __init__(self, headers):
        super().__init__("429")
        self.headers = headers


class _ErroResponseHeaders(Exception):
    def __init__(self, headers):
        super().__init__("429")
        self.response = type("R", (), {"headers": headers})()


def test_retry_after_segundos():
    assert R.retry_after(_ErroHeaders({"Retry-After": "30"})) == 30.0
    assert R.retry_after(_ErroResponseHeaders({"Retry-After": "5"})) == 5.0


def test_retry_after_ausente():
    assert R.retry_after(_ErroHeaders({})) is None
    assert R.retry_after(Exception("sem headers")) is None


def test_retry_after_data_http_ignorada():
    # formato de data HTTP não é suportado -> None (backoff normal assume)
    assert R.retry_after(_ErroHeaders({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})) is None


# --- política e backoff -----------------------------------------------------


class _Rng:
    def __init__(self, v):
        self.v = v

    def random(self):
        return self.v


def _pol(cfg=None):
    return R.PoliticaFalhas(cfg)


def test_backoff_exponencial_sem_jitter():
    pol = _pol()  # base 2, teto 60, jitter 0.5 — rng 0.5 zera o jitter
    r = _Rng(0.5)
    assert R.proxima_espera(0, pol, _rng=r) == 2.0
    assert R.proxima_espera(1, pol, _rng=r) == 4.0
    assert R.proxima_espera(2, pol, _rng=r) == 8.0


def test_backoff_limitado_ao_teto():
    assert R.proxima_espera(10, _pol(), _rng=_Rng(0.5)) == 60.0


def test_retry_after_honrado_ignora_exponencial():
    assert R.proxima_espera(5, _pol(), retry_after_seg=3.0) == 3.0


def test_jitter_dentro_da_faixa():
    pol = _pol()  # jitter 0.5
    assert R.proxima_espera(0, pol, _rng=_Rng(1.0)) == 3.0   # +50%: 2 + 2*0.5
    assert R.proxima_espera(0, pol, _rng=_Rng(0.0)) == 1.0   # -50%: 2 - 2*0.5


def test_jitter_zero_desliga():
    pol = _pol({"backoff": {"base_seg": 2.0, "teto_seg": 60.0, "jitter": 0.0}})
    assert R.proxima_espera(0, pol, _rng=_Rng(0.99)) == 2.0


def test_cap_por_estagio():
    pol = _pol()
    assert pol.cap("roteiro") == 3
    assert pol.cap("visuais") == 2
    assert pol.cap("narracao") == 2
    assert pol.cap("desconhecido") == 3  # fallback


def test_politica_de_tipo(make_tipo):
    tipo = make_tipo("tipo_teste")
    pol = R.de_tipo(tipo)
    assert pol.base == 2.0
    assert pol.failover is True
    assert pol.falha_parcial == "degradar"
