from publicacao.quota import QuotaDiaria, checar_cap


def test_registra_e_conta_por_credencial(tmp_path):
    q = QuotaDiaria(tmp_path / "quota.json")
    assert q.uploads_hoje("youtube:canal") == 0
    q.registrar("youtube:canal")
    q.registrar("youtube:canal")
    assert q.uploads_hoje("youtube:canal") == 2
    # credencial diferente é contada à parte (isolamento por credencial)
    assert q.uploads_hoje("youtube:outro") == 0


def test_ignora_json_corrompido(tmp_path):
    caminho = tmp_path / "quota.json"
    caminho.write_text("{ não é json", encoding="utf-8")
    q = QuotaDiaria(caminho)
    assert q.uploads_hoje("youtube:canal") == 0  # degrada em vez de quebrar


def test_checar_cap_dentro_e_no_limite():
    assert checar_cap(0, 5) is True
    assert checar_cap(4, 5) is True
    assert checar_cap(5, 5) is False  # cap atingido -> adiar
    assert checar_cap(6, 5) is False


def test_checar_cap_zero_e_sem_limite():
    assert checar_cap(999, 0) is True
