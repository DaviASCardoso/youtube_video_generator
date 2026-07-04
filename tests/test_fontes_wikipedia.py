import json

from descoberta.fontes import wikipedia as wiki


def test_e_meta():
    assert wiki._e_meta("Especial:Pesquisar")
    assert wiki._e_meta("Wikipédia:Sobre")
    assert wiki._e_meta("Página_principal")
    assert not wiki._e_meta("Albert_Einstein")


def test_artigos_filtra_meta_e_troca_underscore():
    payload = json.dumps(
        {
            "items": [
                {
                    "articles": [
                        {"article": "Página_principal", "views": 9, "rank": 1},
                        {"article": "Albert_Einstein", "views": 8, "rank": 2},
                        {"article": "Especial:Pesquisar", "views": 7, "rank": 3},
                        {"article": "Machado_de_Assis", "views": 6, "rank": 4},
                    ]
                }
            ]
        }
    )
    assert wiki._artigos(payload, 10) == ["Albert Einstein", "Machado de Assis"]


def test_artigos_respeita_limite():
    payload = json.dumps(
        {"items": [{"articles": [{"article": "A"}, {"article": "B"}, {"article": "C"}]}]}
    )
    assert wiki._artigos(payload, 2) == ["A", "B"]


def test_buscar_monta_candidatos(monkeypatch):
    payload = json.dumps(
        {"items": [{"articles": [{"article": "Tema_Um"}, {"article": "Tema_Dois"}]}]}
    )
    monkeypatch.setattr(wiki, "_baixar", lambda url, timeout=30: payload)
    out = wiki.buscar(None, {"limite": 20})
    assert [c.texto for c in out] == ["Tema Um", "Tema Dois"]
    assert all(c.fonte == "wikipedia" for c in out)
