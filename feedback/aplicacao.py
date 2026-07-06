"""Camada de aplicação: executa uma proposta (numérica/set/guia), reversível.

Aplica um ajuste **já limitado** (o roteador calculou o valor novo dentro do teto) e
registra o valor anterior em `aplicados.json` para permitir reverter. Guia: reescreve
o bloco versionado (preservando vetos por texto). Numérico/set: grava o campo no
`config.json` do tipo (whole-file replace preservando os irmãos, como as abas do painel).

O gate advisory/auto vive no orquestrador (`feedback.processar`): advisory só cria a
proposta; auto chama `aplicar` na hora. `aprovar`/`rejeitar` são as ações do painel.
"""

from feedback import guia
from feedback.armazenamento import aplicados_de, propostas_de


def _get(tipo, path: str):
    try:
        return tipo.config.get(path)
    except Exception:  # noqa: BLE001
        return None


def _set(tipo, path: str, valor) -> None:
    dados = tipo.config.get_all()
    d = dados
    partes = path.split(".")
    for p in partes[:-1]:
        d = d.setdefault(p, {})
    d[partes[-1]] = valor
    tipo.config.salvar(dados)


def aplicar(tipo, proposta: dict) -> dict:
    """Executa a proposta e registra o aplicado (com o valor anterior p/ reverter)."""
    if proposta["tipo"] == "guia":
        bloco = guia.bloco_de(tipo.assets_dir, proposta["bloco"])
        antigas = [l["texto"] for l in bloco.linhas_ativas()]
        conf = float(proposta.get("confianca") or 0.0)
        fonte = f"feedback:{proposta.get('dimensao')}"
        bloco.substituir([guia.linha(t, confianca=conf, fonte=fonte) for t in proposta["linhas_novas"]])
        aplicado = {
            "tipo": "guia",
            "pilar": proposta.get("pilar"),
            "alvo": proposta["alvo"],
            "bloco": proposta["bloco"],
            "dimensao": proposta.get("dimensao"),
            "linhas_antigas": antigas,
            "linhas_novas": proposta["linhas_novas"],
            "proposta_id": proposta.get("id"),
        }
    else:
        path = proposta["alvo"]
        antigo = _get(tipo, path)
        novo = proposta["valor_novo"]
        _set(tipo, path, novo)
        aplicado = {
            "tipo": proposta["tipo"],
            "pilar": proposta.get("pilar"),
            "alvo": path,
            "path": path,
            "dimensao": proposta.get("dimensao"),
            "valor_antigo": antigo,
            "valor_novo": novo,
            "proposta_id": proposta.get("id"),
        }
    return aplicados_de(tipo).registrar(aplicado)


def reverter(tipo, aplicado: dict) -> None:
    """Desfaz um aplicado: restaura o valor/bloco anterior."""
    if aplicado.get("tipo") == "guia":
        guia.bloco_de(tipo.assets_dir, aplicado["bloco"]).substituir(
            [guia.linha(t) for t in aplicado.get("linhas_antigas", [])]
        )
    else:
        _set(tipo, aplicado["path"], aplicado.get("valor_antigo"))


# --- ações do painel (gate advisory) ----------------------------------------


def aprovar(tipo, proposta_id: str) -> dict | None:
    """Aprova & aplica uma proposta pendente. Devolve o aplicado, ou None se sumiu."""
    lojinha = propostas_de(tipo)
    proposta = lojinha.obter(proposta_id)
    if proposta is None or proposta.get("status") != "pendente":
        return None
    aplicado = aplicar(tipo, proposta)
    lojinha.definir_status(proposta_id, "aprovada")
    return aplicado


def rejeitar(tipo, proposta_id: str) -> dict | None:
    """Rejeita uma proposta pendente (não aplica)."""
    return propostas_de(tipo).definir_status(proposta_id, "rejeitada")
