"""Schema e defaults da configuração de Operação por tipo.

Fonte da verdade da forma do bloco `operacao` que cada `tipos/<id>/config.json`
carrega: os defaults (`OPERACAO_PADRAO`) e os enums que o Controle importa para
validar os formulários (mesmo padrão de `descoberta`/`geracao`/`publicacao`/`feedback`).

Este bloco reúne o que é transversal a **rodar** o tipo sem supervisão: quais jobs de
pilar estão ligados, e a **política de resposta a falhas** que o motor de resiliência
aplica — tetos de retry por estágio (mais apertados nos caros), backoff, o circuit
breaker por provedor, se há failover para o alternativo do pilar, a política de falha
parcial (degradar vs. falhar) e as janelas de defer quando o recurso reseta.

Os *valores* dos limites (orçamento em `geracao`, cota em `publicacao`, floor em
`feedback`) continuam nos pilares donos — aqui só vive **como** o motor reage, não
**quanto** cada pilar permite gastar. O agendamento (frequência/horário/fuso) segue no
bloco `agendamento` de cada tipo. Default = o comportamento de hoje (3 retries
transitórios, backoff base 2s, failover aos mesmos alternativos).
"""

import copy

# --- Enums (importados pelo Controle para validar os formulários) -----------

# O que fazer quando parte de um estágio falha (ex.: 3 de 5 imagens): seguir com o
# que deu certo (degradado) ou falhar o run inteiro.
POLITICAS_PARCIAL = ("degradar", "falhar")

# Classes em que o motor de resiliência encaixa cada erro (fonte da verdade das
# chaves; o motor as usa para casar a estratégia).
CLASSES_ERRO = ("transitorio", "permanente", "auth", "quota", "recurso")

# Estágios que o motor conhece (chaves de `caps_por_estagio`). Alinhados aos estágios
# do pipeline da Geração + o upload da Publicação.
ESTAGIOS = ("roteiro", "plano_visual", "visuais", "narracao", "montagem", "publicacao")

# Jobs de pilar cujo liga/desliga o Controle expõe (o agendamento em si fica em
# `agendamento`/`descoberta.antecedencia_horas`/o job global de feedback).
JOBS = ("descoberta", "geracao", "publicacao", "feedback")

# --- Defaults ---------------------------------------------------------------

OPERACAO_PADRAO = {
    "jobs": {  # liga/desliga por job de pilar
        "descoberta": True,
        "geracao": True,
        "publicacao": True,
        "feedback": True,
    },
    "caps_por_estagio": {  # teto de retry (classe transitória) por estágio
        "roteiro": 3,
        "plano_visual": 3,
        "visuais": 2,  # mais apertado: imagem custa
        "narracao": 2,  # mais apertado: TTS custa
        "montagem": 1,
        "publicacao": 2,
    },
    "backoff": {
        "base_seg": 2.0,  # base do crescimento exponencial (base·2^n)
        "teto_seg": 60.0,  # teto de espera por tentativa
        "jitter": 0.5,  # fração de jitter (0–1) para dessincronizar retries
    },
    "circuito": {
        "limiar_falhas": 5,  # falhas consecutivas para abrir o circuito do provedor
        "cooldown_seg": 300,  # tempo aberto antes de um probe meio-aberto
        "janela_saude_seg": 3600,  # janela para o padrão de falhas recentes (adaptatividade)
    },
    "failover": True,  # após esgotar transitórios, cair para o alternativo do pilar
    "falha_parcial": "degradar",  # degradar | falhar
    "defer_horas": {  # defer-para-janela quando o recurso reseta
        "quota": 24,
        "orcamento": 24,
    },
}


# --- Dicas de UI (consumidas pelo motor de formulário do Controle) ----------

UI_HINTS = {
    "jobs": {"rotulo": "Jobs ligados", "ajuda": "Desligue um job para pausar aquele pilar sem desativar o tipo."},
    "jobs.descoberta": {"rotulo": "Descoberta"},
    "jobs.geracao": {"rotulo": "Geração"},
    "jobs.publicacao": {"rotulo": "Publicação"},
    "jobs.feedback": {"rotulo": "Feedback"},
    "caps_por_estagio": {
        "rotulo": "Tetos de retry por estágio",
        "ajuda": "Máximo de retentativas para erros transitórios; mais baixo nos estágios caros (imagem/TTS).",
    },
    "caps_por_estagio.roteiro": {"rotulo": "Roteiro", "min": 0, "max": 10},
    "caps_por_estagio.plano_visual": {"rotulo": "Plano visual", "min": 0, "max": 10},
    "caps_por_estagio.visuais": {"rotulo": "Visuais (imagem)", "min": 0, "max": 10},
    "caps_por_estagio.narracao": {"rotulo": "Narração (TTS)", "min": 0, "max": 10},
    "caps_por_estagio.montagem": {"rotulo": "Montagem", "min": 0, "max": 10},
    "caps_por_estagio.publicacao": {"rotulo": "Upload (publicação)", "min": 0, "max": 10},
    "backoff": {"rotulo": "Backoff"},
    "backoff.base_seg": {"rotulo": "Base (segundos)", "min": 0.0, "max": 60.0, "passo": "0.5"},
    "backoff.teto_seg": {"rotulo": "Teto por tentativa (segundos)", "min": 0.0, "max": 600.0, "passo": "1"},
    "backoff.jitter": {"rotulo": "Jitter (fração 0–1)", "min": 0.0, "max": 1.0, "passo": "0.05"},
    "circuito": {"rotulo": "Circuit breaker por provedor"},
    "circuito.limiar_falhas": {"rotulo": "Falhas para abrir", "min": 1, "max": 50},
    "circuito.cooldown_seg": {"rotulo": "Cooldown aberto (segundos)", "min": 1, "max": 86400},
    "circuito.janela_saude_seg": {"rotulo": "Janela de saúde recente (segundos)", "min": 60, "max": 86400},
    "failover": {"rotulo": "Failover para o provedor alternativo"},
    "falha_parcial": {
        "rotulo": "Falha parcial", "opcoes": POLITICAS_PARCIAL,
        "rotulos_opcoes": {"degradar": "degradar (segue com o que deu certo)", "falhar": "falhar (aborta o run)"},
    },
    "defer_horas": {"rotulo": "Janelas de defer (horas)", "ajuda": "Quando quota/orçamento estoura, reprograma o job para depois deste intervalo."},
    "defer_horas.quota": {"rotulo": "Quota (horas)", "min": 1, "max": 168},
    "defer_horas.orcamento": {"rotulo": "Orçamento (horas)", "min": 1, "max": 168},
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


def mesclar_operacao(bruto: dict | None) -> dict:
    """Completa um bloco `operacao` (parcial ou ausente) com os defaults.

    Deep-merge sobre `OPERACAO_PADRAO`, para que tipos criados antes deste bloco
    existir continuem funcionando (herdam todos os campos novos).

    Args:
        bruto: O bloco `operacao` lido do config.json, ou None.

    Returns:
        Um bloco `operacao` completo.
    """
    if not isinstance(bruto, dict):
        return copy.deepcopy(OPERACAO_PADRAO)
    return _mesclar(OPERACAO_PADRAO, bruto)
