"""Experimentos (costura, off por default).

Fronteira opcional do pilar: rodar e avaliar experimentos simples — variantes de
título, thumbnail ou hook medidas uma contra a outra — quando o volume torna a
comparação significativa. Fica **desligado por default** (`feedback.experimentos.ativo`)
e sem execução ainda: o contrato existe para que Geração/Publicação possam pedir uma
variante e o Feedback avaliar o resultado, sem recablear o pilar quando isso for ligado.

`planejar` devolve `{"ativo": False}` enquanto desligado — os pilares que o consultarem
seguem o caminho normal (sem variante), então ligar/desligar não muda o comportamento
default.
"""

from feedback.configuracao import mesclar_feedback

# Dimensões que um experimento pode variar (quando implementado).
DIMENSOES_EXPERIMENTO = ("titulo", "thumbnail", "hook")


def habilitado(tipo) -> bool:
    """Se os experimentos estão ligados para o tipo."""
    cfg = mesclar_feedback(tipo.config.get_all().get("feedback"))
    return bool(cfg.get("experimentos", {}).get("ativo"))


def planejar(tipo, dimensao: str | None = None) -> dict:
    """Planeja um experimento. Desligado ⇒ `{"ativo": False}` (caminho normal)."""
    if not habilitado(tipo):
        return {"ativo": False, "motivo": "experimentos_desligados", "variantes": []}
    # Costura: sem geração de variantes ainda — o contrato existe, a implementação não.
    return {"ativo": True, "dimensao": dimensao, "variantes": []}


def avaliar(tipo, experimento: dict) -> dict:
    """Avalia um experimento concluído. Costura — sem vencedor até haver execução."""
    return {"ativo": habilitado(tipo), "vencedor": None, "experimento": experimento}
