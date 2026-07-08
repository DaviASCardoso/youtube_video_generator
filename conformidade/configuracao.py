"""Schema e defaults da configuração de Conformidade por tipo.

Fonte da verdade da forma do bloco `conformidade` que cada `tipos/<id>/config.json`
carrega: os defaults (`CONFORMIDADE_PADRAO`) e os enums que o Controle importa para
validar os formulários (mesmo padrão de `descoberta`/`geracao`/`publicacao`/`feedback`/
`operacao`).

A Conformidade é a **consciência** do sistema: ela não produz nada — **veta** e **marca**.
Este bloco reúne apenas o *como* cada checagem se comporta (bloquear vs. advisory) e seus
limiares; o **conteúdo** das regras (listas de brand safety, regra de disclosure, mapa de
licenças) vive versionado por tipo em `conformidade/regras.py`, e a **trilha de auditoria**
em `conformidade/auditoria.py`.

Dois princípios governam o pilar: **checagens objetivas bloqueiam, subjetivas avisam** — um
veto automático sobre julgamento de máquina mataria bons vídeos e faria desligarem o pilar.
Por isso o default é: disclosure e licenciamento **bloqueiam**; brand safety bloqueia o
inequívoco e sinaliza o limítrofe (`equilibrada`); autenticidade e factual são **advisory**;
factual vem **desligada**. E o pilar inteiro nasce **inerte** (`ativo: false`) — ligá-lo é
uma decisão do canal; com ele desligado, o comportamento é idêntico ao de hoje.
"""

import copy

# --- Enums (importados pelo Controle para validar os formulários) -----------

# Como cada checagem age. `bloquear` = veta (objetivo); `advisory` = só sinaliza para o
# humano decidir no gate de revisão (subjetivo); `equilibrada` = veta o caso inequívoco e
# sinaliza o limítrofe (usado pela brand safety, que tem as duas camadas).
MODOS_CHECK = ("advisory", "equilibrada", "bloquear")

# Rigor global do pilar — modula os modos efetivos de cada checagem.
ESTRATEGIAS = ("permissiva", "equilibrada", "estrita")

# As cinco checagens (fonte da verdade das chaves de `checagens`).
CHECAGENS = ("disclosure", "licenciamento", "marca", "autenticidade", "factual")

# --- Defaults ---------------------------------------------------------------

CONFORMIDADE_PADRAO = {
    "ativo": False,  # master: inerte por padrão — com ele desligado nada é checado
    "estrategia": "equilibrada",  # permissiva | equilibrada | estrita
    "checagens": {
        # objetivas → bloqueiam
        "disclosure": {"modo": "bloquear"},
        "licenciamento": {"modo": "bloquear"},
        # brand safety → bloqueia o inequívoco, sinaliza o limítrofe
        "marca": {"modo": "equilibrada"},
        # subjetivas → advisory
        "autenticidade": {
            "modo": "advisory",
            "variacao_minima": 0.25,  # abaixo disso, a proteção de variação é insuficiente
            "teto_sameness": 70,  # sameness (0–100) acima disso → sinaliza slop
            "n_recentes": 5,  # quantos roteiros recentes comparar
        },
        "factual": {"modo": "advisory", "ativo": False},  # a mais difícil de automatizar: um interruptor
    },
}


# --- Dicas de UI (consumidas pelo motor de formulário do Controle) ----------

UI_HINTS = {
    "ativo": {
        "rotulo": "Ativar a Conformidade",
        "ajuda": "Com o pilar desligado, nenhuma checagem roda — o comportamento é o de hoje.",
    },
    "estrategia": {
        "rotulo": "Rigor global",
        "opcoes": ESTRATEGIAS,
        "rotulos_opcoes": {
            "permissiva": "permissiva (afrouxa as subjetivas)",
            "equilibrada": "equilibrada (padrão)",
            "estrita": "estrita (endurece as subjetivas para bloqueio)",
        },
        "ajuda": "Modula os modos efetivos: 'estrita' endurece as checagens de julgamento; 'permissiva' as afrouxa.",
    },
    "checagens": {"rotulo": "Checagens"},
    "checagens.disclosure": {"rotulo": "Disclosure de mídia sintética"},
    "checagens.disclosure.modo": {
        "rotulo": "Modo", "opcoes": MODOS_CHECK,
        "ajuda": "Objetiva: bloqueia uma publicação que omitiria um disclosure exigido.",
    },
    "checagens.licenciamento": {"rotulo": "Licenciamento dos ativos"},
    "checagens.licenciamento.modo": {
        "rotulo": "Modo", "opcoes": MODOS_CHECK,
        "ajuda": "Objetiva: bloqueia um ativo sem origem licenciada.",
    },
    "checagens.marca": {"rotulo": "Brand safety (tema)"},
    "checagens.marca.modo": {
        "rotulo": "Modo", "opcoes": MODOS_CHECK,
        "ajuda": "Veta o tema inequívoco e sinaliza o limítrofe para revisão (equilibrada).",
    },
    "checagens.autenticidade": {"rotulo": "Autenticidade / anti-slop"},
    "checagens.autenticidade.modo": {"rotulo": "Modo", "opcoes": MODOS_CHECK},
    "checagens.autenticidade.variacao_minima": {
        "rotulo": "Variação mínima", "min": 0.0, "max": 1.0, "passo": "0.05",
        "ajuda": "A variação da Geração precisa estar ao menos neste nível para a proteção contar.",
    },
    "checagens.autenticidade.teto_sameness": {
        "rotulo": "Teto de sameness (0–100)", "min": 0, "max": 100,
        "ajuda": "Similaridade com os vídeos recentes acima deste teto → sinaliza.",
    },
    "checagens.autenticidade.n_recentes": {"rotulo": "Nº de recentes a comparar", "min": 1, "max": 20},
    "checagens.factual": {"rotulo": "Precisão factual (opcional)"},
    "checagens.factual.modo": {"rotulo": "Modo", "opcoes": MODOS_CHECK},
    "checagens.factual.ativo": {
        "rotulo": "Ativar a checagem factual",
        "ajuda": "A mais difícil de automatizar — desligada por padrão; quando ligada, é advisory.",
    },
}


def _mesclar(padrao: dict, bruto: dict) -> dict:
    """Deep-merge de `bruto` sobre `padrao` (só desce em dicts; listas/valores
    do `bruto` substituem por inteiro)."""
    resultado = copy.deepcopy(padrao)
    for chave, valor in bruto.items():
        atual = resultado.get(chave)
        if isinstance(atual, dict) and isinstance(valor, dict):
            resultado[chave] = _mesclar(atual, valor)
        else:
            resultado[chave] = copy.deepcopy(valor)
    return resultado


def mesclar_conformidade(bruto: dict | None) -> dict:
    """Completa um bloco `conformidade` (parcial ou ausente) com os defaults.

    Deep-merge sobre `CONFORMIDADE_PADRAO`, para que tipos criados antes deste bloco
    existir continuem funcionando (herdam todos os campos novos).

    Args:
        bruto: O bloco `conformidade` lido do config.json, ou None.

    Returns:
        Um bloco `conformidade` completo.
    """
    if not isinstance(bruto, dict):
        return copy.deepcopy(CONFORMIDADE_PADRAO)
    return _mesclar(CONFORMIDADE_PADRAO, bruto)
