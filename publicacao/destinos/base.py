"""Contrato de destinos da Publicação.

Como as fontes da Descoberta e os provedores da Geração, um **destino** é um papel que
qualquer plataforma preenche atrás de um contrato comum — somar TikTok/Reels/Kwai é
implementar o contrato, não recablear o pilar. Cada destino tem seu liga/desliga e sua
credencial isolada (uma falha/cota de um canal não afeta outro).

Contrato de um `Destino`:
- `nome` — chave do destino (== chave em `publicacao.destinos`).
- `publicar(video_path, metadados, thumb_path, opcoes, tipo) -> dict` — sobe o vídeo e
  devolve `{id, url, quota}` (+ o que mais quiser registrar).
- `checar_credencial(tipo) -> {status, detalhe}` — verificação não-destrutiva do
  ciclo de vida da credencial (valido / expirando / expirado / ausente).

O registro é populado ao importar os módulos de destino; `obter()` garante o import
tardio (evita ciclo com este módulo), no mesmo padrão de `geracao.provedores.base`.
"""

_REGISTRO: dict[str, type] = {}


def registrar(nome: str):
    """Decorador de classe: registra um destino sob `nome`."""

    def _deco(cls):
        cls.nome = nome
        _REGISTRO[nome] = cls
        return cls

    return _deco


def _garantir_carregado() -> None:
    from publicacao.destinos import youtube  # noqa: F401 (auto-registro)


def obter(nome: str):
    """Instancia o destino registrado sob `nome`."""
    _garantir_carregado()
    try:
        cls = _REGISTRO[nome]
    except KeyError:
        raise KeyError(f"destino não registrado: {nome!r}")
    return cls()


def disponiveis() -> list[str]:
    """Nomes de destinos registrados (implementados)."""
    _garantir_carregado()
    return sorted(_REGISTRO)
