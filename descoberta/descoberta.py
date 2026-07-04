"""Orquestrador da Descoberta: decide o único tema do tipo para o próximo vídeo.

`decidir_tema(tipo)` junta tudo, respeitando a eficiência (o passo caro — LLM —
só nos top contenders) e a configurabilidade (tudo lido do bloco `descoberta` do
tipo). Fluxo:

  fontes ativas → candidatos → dedup → pré-rank barato → fit dos top N →
  seleção ponderada → 1 tema decidido → (gate) pronto|pendente

Grava o tema no slot do tipo, registra o sinal consumido (dedupe futuro) e a
observabilidade do run. Devolve a Decisao, ou None se nada passou (dia pulado).
"""

from descoberta import balanco, dedup, fit, selecao, estado
from descoberta.candidato import Decisao, agora
from descoberta.configuracao import FONTES_DISPONIVEIS, mesclar_descoberta
from descoberta.fontes import base
from descoberta.tendencias import historico_tendencias

# Importa os módulos de fonte para disparar o registro (@base.registrar).
from descoberta.fontes import (  # noqa: F401
    google_trends,
    pool,
    reddit,
    trends_mcp,
    wikipedia,
    youtube,
)

# Quantos temas decididos recentes olhar para o balanço trending/evergreen.
_JANELA_BALANCO = 10


def _coletar(tipo, cfg: dict) -> tuple[list, dict]:
    """Coleta candidatos de todas as fontes ativas. Devolve (candidatos, contagem)."""
    coletados = []
    contagem = {}
    for nome in FONTES_DISPONIVEIS:
        cfg_fonte = cfg["fontes"].get(nome, {})
        if not cfg_fonte.get("ativo"):
            continue
        cands = base.coletar(nome, tipo, cfg_fonte)
        contagem[nome] = len(cands)
        coletados.extend(cands)
    return coletados, contagem


def decidir_tema(tipo, persistir: bool = True) -> Decisao | None:
    """Roda um ciclo de descoberta e decide (no máximo) um tema para o tipo.

    Args:
        tipo: O tipo de vídeo.
        persistir: Se False (dry-run), não grava slot/buffer/histórico nem
            registra o sinal consumido — só calcula e devolve a decisão.

    Returns:
        A Decisao (estado "pronto" em modo auto, "pendente" em modo revisar), ou
        None se nenhum candidato foi aprovado.
    """
    cfg = mesclar_descoberta(tipo.config.get_all().get("descoberta"))
    hist = estado.historico_de(tipo)
    agora_dt = agora()

    categoria_ciclo = balanco.categoria_do_ciclo(
        hist.categorias_recentes(_JANELA_BALANCO), cfg["evergreen_ratio"]
    )

    coletados, contagem = _coletar(tipo, cfg)

    retidos = estado.buffer_de(tipo).listar() if cfg["retencao"] == "reter" else []

    # dedup contra sinais consumidos + temas já decididos
    dias = cfg["dedup"]["dias"]
    ja_vistos = dedup.sinais_recentes(tipo, dias) | hist.temas_decididos_recentes(dias)
    candidatos = dedup.filtrar(coletados + retidos, ja_vistos, cfg)

    minimo = cfg["fit"]["score_minimo"]
    novos = [c for c in candidatos if c.fit_score is None]
    # retidos que já passaram no mínimo antes (não reavaliar)
    reaproveitados = [
        c for c in candidatos if c.fit_score is not None and c.fit_score >= minimo
    ]

    # pré-rank barato (força × frescor), com bônus para a categoria do ciclo
    def _chave(c):
        bonus = 1 if c.categoria == categoria_ciclo else 0
        fr = selecao.frescor(c.observado_em, agora_dt, cfg["selecao"]["meia_vida_horas"])
        return (bonus, c.forca_sinal * fr)

    novos.sort(key=_chave, reverse=True)
    contenders = novos[: cfg["orcamento_avaliacao"]]

    aprovados = []
    for c in contenders:
        if fit.avaliar(c, tipo, cfg):  # passo caro (LLM), preenche o candidato
            aprovados.append(c)

    elegiveis = aprovados + reaproveitados
    melhor, pontuacao = selecao.selecionar(elegiveis, cfg["selecao"], agora_dt)

    base_registro = {
        "categoria_ciclo": categoria_ciclo,
        "fontes": contagem,
        "coletados": len(coletados),
        "retidos": len(retidos),
        "apos_dedup": len(candidatos),
        "avaliados": len(contenders),
    }

    if melhor is None:
        if persistir:
            hist.registrar({**base_registro, "decidido": None, "motivo": "nenhum_aprovado"})
            if cfg["retencao"] == "reter":
                estado.buffer_de(tipo).substituir(reaproveitados)
        return None

    estado_gate = "pronto" if cfg["modo_revisao"] == "auto" else "pendente"
    decisao = Decisao(
        tema=melhor.tema or melhor.texto,
        fonte=melhor.fonte,
        categoria=melhor.categoria,
        fit_score=melhor.fit_score or 0.0,
        justificativa=melhor.justificativa or "",
        prioridade=pontuacao,
        estado=estado_gate,
    )

    if persistir:
        estado.slot_de(tipo).gravar(decisao)
        historico_tendencias.registrar(tipo.id, melhor.texto, melhor.fonte, decisao.tema)
        hist.registrar({**base_registro, "decidido": decisao.para_dict(), "motivo": "ok"})
        if cfg["retencao"] == "reter":
            nao_escolhidos = [c for c in elegiveis if c is not melhor]
            estado.buffer_de(tipo).substituir(nao_escolhidos)
        else:
            estado.buffer_de(tipo).limpar()

    return decisao


if __name__ == "__main__":
    import sys

    from config.tipos import carregar_tipo

    seco = "--commit" not in sys.argv
    if seco:
        print("Rodando em DRY-RUN (não grava o slot). Use --commit para valer.\n")

    tipo = carregar_tipo("cetico_pratico")
    decisao = decidir_tema(tipo, persistir=not seco)
    if decisao is None:
        print("Nenhum tema aprovado neste ciclo.")
    else:
        print(f"tema:          {decisao.tema}")
        print(f"fonte:         {decisao.fonte}")
        print(f"categoria:     {decisao.categoria}")
        print(f"fit_score:     {decisao.fit_score}")
        print(f"prioridade:    {decisao.prioridade:.3f}")
        print(f"estado:        {decisao.estado}")
        print(f"justificativa: {decisao.justificativa}")
