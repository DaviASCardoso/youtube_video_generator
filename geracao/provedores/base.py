"""Contrato de provedores por estágio da Geração.

Cada estágio que gasta dinheiro (roteiro, plano+render de visuais, narração) é
atendido por um **provedor plugável**, selecionado por config
(`geracao.<estagio>.provedor`). Um provedor embrulha a chamada externa concreta
(Groq, FLUX/Together, Pexels+compositor, Google TTS), reporta o custo estimado da
operação num `Ledger`, e expõe uma interface uniforme para o runner de estágios do
pipeline. Assim, trocar de provedor (ou somar um novo, ex.: ElevenLabs na narração)
é registrar uma classe — sem tocar no pipeline.

Papéis e a forma de cada um:
- **roteiro**  → `gerar(tema, config, assets_dir, variacao=None, ledger=None) -> [(i, frase)]`
- **visuais**  → `planejar(frases, config, assets_dir, variacao=None, ledger=None) -> [dado_cena]`
                 e `renderizar(indice, dado, config, assets_dir, variacao=None, ledger=None) -> bytes | Image`
- **narracao** → `narrar(texto, caminho_saida, config, voz=None, ledger=None) -> Path`

O registro é populado ao importar os módulos de provedor; `obter()` garante que
eles foram carregados (import tardio, evitando ciclo com este módulo).
"""

PAPEL_ROTEIRO = "roteiro"
PAPEL_VISUAIS = "visuais"
PAPEL_NARRACAO = "narracao"

_REGISTRO: dict[tuple[str, str], type] = {}


def registrar(papel: str, nome: str):
    """Decorador de classe: registra um provedor sob (papel, nome)."""

    def _deco(cls):
        cls.papel = papel
        cls.nome = nome
        _REGISTRO[(papel, nome)] = cls
        return cls

    return _deco


def _garantir_carregado() -> None:
    """Importa os módulos de provedor (que se auto-registram). Import tardio para
    não criar ciclo: os provedores importam deste módulo."""
    from geracao.provedores import (  # noqa: F401
        narracao_google,
        roteiro_groq,
        visuais_flux,
        visuais_pexels,
    )


def obter(papel: str, nome: str):
    """Instancia o provedor registrado para (papel, nome)."""
    _garantir_carregado()
    try:
        cls = _REGISTRO[(papel, nome)]
    except KeyError:
        raise KeyError(f"provedor não registrado: papel={papel!r} nome={nome!r}")
    return cls()


def provedores_de(papel: str) -> list[str]:
    """Nomes registrados para um papel (ordenados)."""
    _garantir_carregado()
    return sorted(n for (p, n) in _REGISTRO if p == papel)


def provedor_visuais_para_fundo(fundo: str) -> str:
    """Deriva o provedor de visuais a partir da **fonte do fundo** (a camada de
    background), quando `geracao.visuais.provedor` está em "auto". "ia" → flux
    (FLUX/Together), "pexels" → pexels. A seleção do provedor segue a fonte do fundo
    escolhida, não mais o modo empacotado (aposentado)."""
    return "pexels" if fundo == "pexels" else "flux"


def provedor_visuais_para_modo(modo: str) -> str:
    """Compat: deriva o provedor do legado `imagens.modo`. "ia" → flux,
    "personagem" → pexels. Prefira `provedor_visuais_para_fundo`."""
    return "pexels" if modo == "personagem" else "flux"
