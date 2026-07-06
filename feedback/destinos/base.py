"""Contrato de destinos de analytics do Feedback.

Como os destinos da Publicação, um **destino de analytics** é um papel que qualquer
plataforma preenche atrás de um contrato comum — somar outra plataforma é implementar
o contrato, não recablear o pilar. Só o YouTube está implementado; os demais são costura.

Contrato de um `Destino`:
- `nome` — chave do destino (== chave em `feedback.destinos`).
- `metricas_do_video(tipo, video_id, publicado_em) -> dict | None` — puxa métricas +
  curva de retenção de um vídeo; `None` quando nada pôde ser lido (mantém último dado).
- `checar(tipo) -> {status, detalhe}` — verificação não-destrutiva da credencial.

O registro é populado ao importar os módulos de destino; `obter()` faz o import tardio
(evita ciclo), no mesmo padrão de `publicacao.destinos.base`.
"""

_REGISTRO: dict[str, type] = {}


def registrar(nome: str):
    """Decorador de classe: registra um destino de analytics sob `nome`."""

    def _deco(cls):
        cls.nome = nome
        _REGISTRO[nome] = cls
        return cls

    return _deco


def _garantir_carregado() -> None:
    from feedback.destinos import youtube  # noqa: F401 (auto-registro)


def obter(nome: str):
    """Instancia o destino registrado sob `nome`."""
    _garantir_carregado()
    try:
        cls = _REGISTRO[nome]
    except KeyError:
        raise KeyError(f"destino de analytics não registrado: {nome!r}")
    return cls()


def disponiveis() -> list[str]:
    """Nomes de destinos registrados (implementados)."""
    _garantir_carregado()
    return sorted(_REGISTRO)
