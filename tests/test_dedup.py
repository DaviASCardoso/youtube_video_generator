from descoberta import dedup
from descoberta.candidato import Candidato, agora
from descoberta.configuracao import DESCOBERTA_PADRAO


def _cand(texto):
    return Candidato(texto=texto, fonte="x", forca_sinal=0.5, observado_em=agora())


def test_repetido_exato():
    vistos = {"foco e disciplina"}
    assert dedup.repetido("Foco e Disciplina", vistos, "exato", 0.8)
    assert not dedup.repetido("Produtividade", vistos, "exato", 0.8)


def test_repetido_exato_nao_pega_reescrita():
    vistos = {"como ter foco no trabalho"}
    assert not dedup.repetido("foco no trabalho", vistos, "exato", 0.8)


def test_repetido_token_pega_reescrita():
    vistos = {"como ter mais foco no trabalho"}
    # sobreposição alta de tokens
    assert dedup.repetido("ter mais foco no trabalho", vistos, "token", 0.6)


def test_repetido_token_abaixo_do_limiar():
    vistos = {"foco no trabalho"}
    assert not dedup.repetido("receita de bolo de cenoura", vistos, "token", 0.5)


def test_repetido_texto_vazio():
    assert not dedup.repetido("   ", {"algo"}, "exato", 0.8)


def test_filtrar_remove_repetidos():
    vistos = {"tema a"}
    cands = [_cand("Tema A"), _cand("Tema B")]
    restantes = dedup.filtrar(cands, vistos, DESCOBERTA_PADRAO)
    assert [c.texto for c in restantes] == ["Tema B"]


def test_sinais_recentes_le_historico(make_tipo, monkeypatch, tmp_path):
    from descoberta.tendencias import HistoricoTendencias

    tipo = make_tipo()
    h = HistoricoTendencias(tmp_path / "hist.json")
    h.registrar(tipo.id, "Trend Usada", "Google Trends", "tema")
    monkeypatch.setattr(dedup, "historico_tendencias", h)
    assert "trend usada" in dedup.sinais_recentes(tipo, dias=14)
