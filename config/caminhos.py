"""Raízes de armazenamento do sistema — a fonte única de resolução de caminhos.

Onde os dados vivem no disco: saída/render (`saida`), histórico + logs de execução
(`execucoes`), o store de dedupe da Descoberta (`tendencias`) e o conteúdo por tipo
(`tipos`, i.e. tipos/<id>/). Todos são resolvidos aqui a partir de `config.sistema`,
de modo que trocar o ajuste no painel realoca os dados **sem editar código** — para
apontar tudo num mount (NAS), por exemplo. Os padrões apontam exatamente para os
locais de hoje, então nada se move até o ajuste mudar.

Um caminho relativo é ancorado na raiz do repositório (mesmo lugar que as constantes
antigas resolviam); um absoluto é usado como está. As lojas criadas no import de um
módulo (histórico, cota, circuitos, ...) leem a config no import — trocar a raiz pede
um restart para elas; a resolução de tipos e da saída é feita a cada chamada.

`garantir_raizes()` cria a árvore de cada raiz no startup e reporta o que não pôde ser
criado/gravado (um mount ausente ou somente-leitura vira sinal claro, não um crash lá
no meio de um run); `verificar_raiz()` alimenta o dashboard de saúde.
"""

import os
from pathlib import Path

from config.sistema import sistema

_REPO = Path(__file__).parent.parent

# Nome lógico -> (chave de config em sistema.json, local padrão relativo à raiz do repo).
_RAIZES = {
    "saida": ("saida.pasta_base", "output"),
    "execucoes": ("caminhos.execucoes", "execucoes"),
    "tendencias": ("caminhos.tendencias", "tendencias"),
    "tipos": ("caminhos.tipos", "tipos"),
}

NOMES = tuple(_RAIZES)


def _bruto(nome: str) -> str:
    """Valor cru configurado para a raiz `nome` (cai no padrão se ausente/vazio)."""
    chave, padrao = _RAIZES[nome]
    try:
        valor = sistema.get(chave)
    except KeyError:
        valor = padrao
    valor = str(valor).strip() if valor is not None else ""
    return valor or padrao


def raiz(nome: str) -> Path:
    """Resolve e normaliza a raiz base `nome` para um Path absoluto.

    Um caminho relativo é ancorado na raiz do repositório; `~` é expandido.

    Raises:
        KeyError: se `nome` não for uma raiz conhecida.
    """
    if nome not in _RAIZES:
        raise KeyError(f"Raiz de caminho desconhecida: {nome!r}")
    p = Path(_bruto(nome)).expanduser()
    if not p.is_absolute():
        p = _REPO / p
    return Path(os.path.normpath(p))


def _gravavel(caminho: Path) -> bool:
    """Tenta criar a árvore e confere se dá para gravar (um NAS pode estar
    ausente ou somente-leitura). Nunca levanta — devolve False no problema."""
    try:
        caminho.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(caminho, os.W_OK)


def verificar_raiz(nome: str) -> dict:
    """Estado de uma raiz para o dashboard: existe? é gravável? — sem levantar erro."""
    caminho = raiz(nome)
    gravavel = _gravavel(caminho)
    return {
        "nome": nome,
        "caminho": str(caminho),
        "existe": caminho.exists(),
        "gravavel": gravavel,
        "ok": gravavel,
    }


def verificar_raizes() -> list[dict]:
    """Estado de todas as raízes (para o dashboard de saúde)."""
    return [verificar_raiz(nome) for nome in _RAIZES]


def garantir_raizes() -> list[dict]:
    """Cria a árvore de cada raiz no startup e devolve os problemas (raiz ausente/
    somente-leitura). **Não levanta**: o painel precisa subir para o ajuste poder ser
    corrigido; quem chama loga a mensagem acionável e o dashboard mostra o sinal."""
    return [estado for estado in verificar_raizes() if not estado["ok"]]


def mensagem_problemas(problemas: list[dict]) -> str:
    """Mensagem acionável para raízes indisponíveis (usada no log de startup)."""
    linhas = [
        f"  - {p['nome']}: {p['caminho']} (ausente ou não gravável)" for p in problemas
    ]
    return (
        "AVISO: caminho(s) de armazenamento configurado(s) indisponível(is):\n"
        + "\n".join(linhas)
        + "\n         Verifique o mount/permissões ou ajuste em /configuracoes. "
        "Runs que gravem nessa raiz vão falhar até ser corrigido."
    )
