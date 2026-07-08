from conformidade.auditoria import Auditoria, auditoria_de
from conformidade.parecer import (
    BLOQUEADO,
    FLAG,
    LIBERADO,
    PASSOU,
    Checagem,
    Parecer,
    Veredito,
)


def _store(tmp_path):
    return Auditoria(tmp_path / "conformidade" / "auditoria.json")


# --- Auditoria ---------------------------------------------------------------


def test_registrar_carimba_quando_e_ordena(tmp_path):
    a = _store(tmp_path)
    a.registrar({"etapa": "descoberta", "tema": "primeiro"})
    r2 = a.registrar({"etapa": "publicacao", "tema": "segundo"})
    assert "quando" in r2
    lista = a.listar()
    assert [r["tema"] for r in lista] == ["segundo", "primeiro"]  # mais recente primeiro


def test_quando_explicito_preservado(tmp_path):
    a = _store(tmp_path)
    a.registrar({"tema": "x", "quando": "2026-01-01T00:00:00+00:00"})
    assert a.listar()[0]["quando"] == "2026-01-01T00:00:00+00:00"


def test_de_execucao_filtra(tmp_path):
    a = _store(tmp_path)
    a.registrar({"execucao_id": "E1", "tema": "a"})
    a.registrar({"execucao_id": "E2", "tema": "b"})
    a.registrar({"execucao_id": "E1", "tema": "c"})
    assert {r["tema"] for r in a.de_execucao("E1")} == {"a", "c"}
    assert a.de_execucao("E9") == []


def test_arquivo_corrompido_vira_lista_vazia(tmp_path):
    caminho = tmp_path / "conformidade" / "auditoria.json"
    caminho.parent.mkdir(parents=True)
    caminho.write_text("não json", encoding="utf-8")
    assert Auditoria(caminho).listar() == []


def test_persistido_entre_instancias(tmp_path):
    caminho = tmp_path / "conformidade" / "auditoria.json"
    Auditoria(caminho).registrar({"tema": "x"})
    assert len(Auditoria(caminho).listar()) == 1


def test_auditoria_de_usa_pasta_do_tipo(make_tipo):
    tipo = make_tipo()
    auditoria_de(tipo).registrar({"tema": "t"})
    assert (tipo.caminho / "conformidade" / "auditoria.json").exists()


# --- parecer shapes ----------------------------------------------------------


def test_veredito_helpers():
    assert Veredito(BLOQUEADO, "termo proibido").bloqueado is True
    assert Veredito(FLAG).sinalizado is True
    v = Veredito(LIBERADO)
    assert not v.bloqueado and not v.sinalizado
    assert v.para_dict() == {"resultado": "liberado", "motivo": ""}


def test_parecer_para_dict():
    p = Parecer(
        bloqueado=True,
        motivos_bloqueio=["ativo sem licença: musica"],
        flags=["sameness alta"],
        disclosure_requer=True,
        disclosure_base="narração sintética + visual realista",
        checagens=[Checagem("disclosure", PASSOU), Checagem("licenciamento", BLOQUEADO, "musica")],
    )
    d = p.para_dict()
    assert d["bloqueado"] is True
    assert d["disclosure"] == {"requer": True, "base": "narração sintética + visual realista"}
    assert d["flags"] == ["sameness alta"]
    assert d["checagens"][1] == {"nome": "licenciamento", "resultado": "bloqueado", "detalhe": "musica"}


def test_parecer_default_vazio():
    p = Parecer()
    assert p.bloqueado is False
    assert p.flags == [] and p.motivos_bloqueio == [] and p.checagens == []
    assert p.para_dict()["disclosure"] == {"requer": False, "base": ""}
