from geracao.variacao import Variacao


def test_intensidade_zero_e_identidade():
    v = Variacao({"aberturas": 0.0, "estrutura": 0.0, "estilo_visual": 0.0})
    assert v.abertura() is None
    assert v.estrutura() is None
    assert v.estilo_visual() is None
    assert v.aplicar_ao_roteiro("SYS") == "SYS"
    assert v.aplicar_ao_estilo("estilo base") == "estilo base"


def test_intensidade_um_sempre_varia():
    v = Variacao({"aberturas": 1.0, "estrutura": 1.0, "estilo_visual": 1.0}, semente=1)
    assert v.abertura() is not None
    assert v.estrutura() is not None
    assert v.estilo_visual() is not None


def test_semente_e_deterministica():
    a = Variacao({"aberturas": 1.0}, semente=42).abertura()
    b = Variacao({"aberturas": 1.0}, semente=42).abertura()
    assert a == b


def test_sementes_diferentes_divergem():
    escolhas = {
        Variacao({"aberturas": 1.0}, semente=s).abertura() for s in range(20)
    }
    assert len(escolhas) > 1  # não colapsa numa única abertura


def test_aplicar_ao_roteiro_anexa_diretrizes():
    v = Variacao({"aberturas": 1.0, "estrutura": 1.0}, semente=3)
    out = v.aplicar_ao_roteiro("Persona base.")
    assert out.startswith("Persona base.")
    assert len(out) > len("Persona base.")


def test_aplicar_ao_estilo_anexa_modificador():
    v = Variacao({"estilo_visual": 1.0}, semente=3)
    out = v.aplicar_ao_estilo("cartoon 3d")
    assert out.startswith("cartoon 3d,")


def test_aplicar_ao_estilo_com_base_vazia():
    v = Variacao({"estilo_visual": 1.0}, semente=3)
    out = v.aplicar_ao_estilo("")
    assert out and not out.startswith(",")


def test_musica_lista_vazia():
    assert Variacao({"musica": 1.0}).musica([]) is None


def test_musica_sem_variacao_pega_a_primeira():
    v = Variacao({"musica": 0.0})
    assert v.musica(["a.mp3", "b.mp3", "c.mp3"]) == "a.mp3"


def test_musica_varia_entre_faixas():
    faixas = ["a.mp3", "b.mp3", "c.mp3"]
    escolhas = {
        Variacao({"musica": 1.0}, semente=s).musica(faixas) for s in range(20)
    }
    assert len(escolhas) > 1
