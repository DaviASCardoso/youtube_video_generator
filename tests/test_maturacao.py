from datetime import datetime, timedelta, timezone

from feedback import maturacao

PUB = "2026-07-01T00:00:00+00:00"
REPOLL = [24, 72, 168, 720]


def _em(horas):
    return datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(hours=horas)


def test_horas_desde():
    assert maturacao.horas_desde(PUB, _em(48)) == 48.0


def test_nenhum_marco_antes_de_24h():
    assert maturacao.marcos_devidos(PUB, REPOLL, [], _em(10)) == []
    assert maturacao.alvo(PUB, REPOLL, [], _em(10)) is None


def test_primeiro_marco_apos_24h():
    assert maturacao.marcos_devidos(PUB, REPOLL, [], _em(25)) == [24]
    assert maturacao.alvo(PUB, REPOLL, [], _em(25)) == 24


def test_dois_marcos_devidos_pega_o_maior():
    assert maturacao.marcos_devidos(PUB, REPOLL, [], _em(100)) == [24, 72]
    assert maturacao.alvo(PUB, REPOLL, [], _em(100)) == 72


def test_ja_coletados_sao_excluidos():
    assert maturacao.marcos_devidos(PUB, REPOLL, [24], _em(100)) == [72]
    assert maturacao.marcos_devidos(PUB, REPOLL, ["24", "72"], _em(100)) == []


def test_marco_string_ou_int_indiferente():
    # os polls são keyed por str no store; 24 já coletado, 72 e 168 devidos a 200h
    assert maturacao.marcos_devidos(PUB, REPOLL, {"24": {}}, _em(200)) == [72, 168]


def test_maturado_quando_todos_coletados():
    assert maturacao.maturado(PUB, REPOLL, [24, 72, 168, 720]) is True
    assert maturacao.maturado(PUB, REPOLL, [24, 72]) is False


def test_apos_720h_ultimo_marco():
    assert maturacao.marcos_devidos(PUB, REPOLL, [24, 72, 168], _em(800)) == [720]
    # depois de coletar o último, nada mais e maturado
    assert maturacao.alvo(PUB, REPOLL, [24, 72, 168, 720], _em(2000)) is None
    assert maturacao.maturado(PUB, REPOLL, [24, 72, 168, 720]) is True


def test_publicado_em_sem_timezone_assume_utc():
    assert maturacao.horas_desde("2026-07-01T00:00:00", _em(24)) == 24.0
