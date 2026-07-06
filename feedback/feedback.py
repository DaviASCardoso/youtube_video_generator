"""Orquestrador do Feedback: atribui → agrega → roteia → propõe (ou auto-aplica).

`processar(tipo)` fecha o laço da metade "aplicar": lê os vetores atribuídos, agrega em
findings (guardados para o Controle), escolhe o vencedor de cada dimensão roteável e
gera propostas — numéricas/set via `roteador`, textuais via `traducao` (Groq). O gate é
por alvo: `advisory` (default) só cria a proposta e espera aprovação humana; `auto`
aplica na hora. É eficiente e degradável:

- não recomputa agregados se a assinatura dos inputs não mudou;
- não retraduz/duplicata: pula quando já há proposta pendente para o mesmo alvo;
- o `traduzir` degrada para None (mantém o último bloco) e o `propor` para None (sem
  mudança), então uma passada sem novidade não faz nada.

Não faz ingestão — quem puxa métricas é `ingestao.ingerir`; o job de Operações chama os
dois em sequência.
"""

from feedback import aplicacao, atribuicao, agregacao, roteador, traducao
from feedback.armazenamento import findings_de, propostas_de
from feedback.configuracao import mesclar_feedback


def processar(tipo) -> dict:
    """Uma passada de processamento para o tipo. Devolve um resumo observável."""
    cfg = mesclar_feedback(tipo.config.get_all().get("feedback"))

    vetores = atribuicao.atribuir(tipo)
    if not vetores:
        return {"pulado": "sem_dados", "propostas": [], "aplicados": []}

    findings_store = findings_de(tipo)
    assinatura = agregacao.assinatura(vetores)
    if assinatura == findings_store.assinatura():
        return {"pulado": "inalterado", "propostas": [], "aplicados": []}

    findings = agregacao.agregar(vetores, cfg)
    findings_store.substituir(findings, assinatura)

    modos = cfg.get("aplicacao", {})
    lojinha = propostas_de(tipo)
    resumo = {"findings": len(findings), "propostas": [], "aplicados": []}

    for finding in roteador.melhores_por_dimensao(findings):
        rota = roteador.classificar(finding["dimensao"])
        if rota is None:
            continue
        chave = f"guia:{rota['bloco']}" if rota["classe"] == "guia" else rota["alvo"]
        if lojinha.existe_equivalente(chave):
            continue  # já há uma proposta pendente para este alvo (evita duplicar/retraduzir)

        if rota["classe"] == "guia":
            proposta = traducao.propor_guia(tipo, finding, cfg)
        else:
            proposta = roteador.propor(finding, tipo, cfg)
        if proposta is None:
            continue

        modo = modos.get(rota["pilar"], "advisory")
        if modo == "auto":
            aplicado = aplicacao.aplicar(tipo, proposta)
            resumo["aplicados"].append({"alvo": proposta["alvo"], "dimensao": finding["dimensao"]})
        else:
            reg = lojinha.adicionar(proposta)
            resumo["propostas"].append(reg["id"])

    return resumo
