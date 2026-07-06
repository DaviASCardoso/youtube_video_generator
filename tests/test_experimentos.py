from feedback import experimentos
from feedback.configuracao import mesclar_feedback


def test_desligado_por_default(make_tipo):
    tipo = make_tipo("tipo_teste")
    assert experimentos.habilitado(tipo) is False
    p = experimentos.planejar(tipo, "titulo")
    assert p["ativo"] is False
    assert p["motivo"] == "experimentos_desligados"


def test_ligado_planeja_costura(make_tipo):
    cfg = mesclar_feedback({"experimentos": {"ativo": True}})
    tipo = make_tipo("tipo_teste", config_extra={"feedback": cfg})
    assert experimentos.habilitado(tipo) is True
    p = experimentos.planejar(tipo, "hook")
    assert p["ativo"] is True
    assert p["dimensao"] == "hook"
    assert p["variantes"] == []


def test_avaliar_sem_vencedor(make_tipo):
    tipo = make_tipo("tipo_teste")
    r = experimentos.avaliar(tipo, {"id": "exp1"})
    assert r["vencedor"] is None
