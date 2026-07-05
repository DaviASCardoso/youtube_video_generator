from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api.schemas import GeracaoConfig
from api.templating import templates
from config.tipos import TipoVideo, carregar_tipo
from geracao.compositor import POSICOES as POSICOES_PERSONAGEM  # noqa: F401 (reservado)
from geracao.configuracao import (
    ACOES_ORCAMENTO,
    FALLBACKS_VISUAIS,
    POSICOES_LEGENDA,
    PROVEDORES_NARRACAO,
    PROVEDORES_ROTEIRO,
    PROVEDORES_VISUAIS,
    mesclar_geracao,
)
from operacoes import execucoes as execucoes_mod
from operacoes import scheduler as scheduler_mod

router = APIRouter(prefix="/tipos/{id}/geracao", tags=["geracao"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _enums() -> dict:
    return {
        "provedores_roteiro": PROVEDORES_ROTEIRO,
        "provedores_visuais": PROVEDORES_VISUAIS,
        "provedores_narracao": PROVEDORES_NARRACAO,
        "fallbacks_visuais": FALLBACKS_VISUAIS,
        "acoes_orcamento": ACOES_ORCAMENTO,
        "posicoes_legenda": POSICOES_LEGENDA,
    }


def _runs_geracao(tipo: TipoVideo) -> list[dict]:
    """Últimas execuções do tipo, para a observabilidade de custo/provedor."""
    return execucoes_mod.historico.listar(tipo.id)[:8]


def contexto_geracao(tipo: TipoVideo) -> dict:
    """Contexto para renderizar a aba Geração (usado também na página de edição)."""
    return {
        "tipo": tipo,
        "g": mesclar_geracao(tipo.config.get_all().get("geracao")),
        "runs_geracao": _runs_geracao(tipo),
        **_enums(),
    }


def _render(tipo_id, request, g, erro=None, sucesso=False, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "g": g,
        "runs_geracao": _runs_geracao(tipo),
        "erro": erro,
        "sucesso": sucesso,
        **_enums(),
    }
    return templates.TemplateResponse("_tipos_geracao_tab.html", ctx, status_code=status_code)


@router.post("", response_class=HTMLResponse)
def salvar(
    id: str,
    request: Request,
    roteiro_provedor: str = Form(...),
    roteiro_duracao_alvo_seg: int = Form(...),
    roteiro_tom: str = Form(""),
    roteiro_min_palavras: int = Form(...),
    roteiro_max_palavras: int = Form(...),
    visuais_provedor: str = Form(...),
    visuais_imagens_por_cena: int = Form(...),
    visuais_fallback: str = Form(...),
    narracao_provedor: str = Form(...),
    narracao_voz_secundaria: str = Form(""),
    legendas_ativo: str | None = Form(None),
    legendas_tamanho: int = Form(...),
    legendas_cor: str = Form(...),
    legendas_posicao: str = Form(...),
    musica_ativo: str | None = Form(None),
    musica_arquivo: str = Form(""),
    montagem_intro: str = Form(""),
    montagem_outro: str = Form(""),
    variacao_aberturas: float = Form(...),
    variacao_estrutura: float = Form(...),
    variacao_musica: float = Form(...),
    variacao_estilo_visual: float = Form(...),
    variacao_semente: str = Form(""),
    orcamento_por_video_usd: float = Form(...),
    orcamento_por_dia_usd: float = Form(...),
    orcamento_acao: str = Form(...),
    checkpoint_reaproveitar: str | None = Form(None),
):
    semente = int(variacao_semente) if variacao_semente.strip() else None
    dados = {
        "roteiro": {
            "provedor": roteiro_provedor,
            "duracao_alvo_seg": roteiro_duracao_alvo_seg,
            "tom": roteiro_tom.strip(),
            "min_palavras": roteiro_min_palavras,
            "max_palavras": roteiro_max_palavras,
        },
        "visuais": {
            "provedor": visuais_provedor,
            "imagens_por_cena": visuais_imagens_por_cena,
            "fallback": visuais_fallback,
        },
        "narracao": {
            "provedor": narracao_provedor,
            "voz_secundaria": narracao_voz_secundaria.strip(),
        },
        "legendas": {
            "ativo": legendas_ativo is not None,
            "tamanho": legendas_tamanho,
            "cor": legendas_cor.strip(),
            "posicao": legendas_posicao,
        },
        "montagem": {
            "musica_fundo": {"ativo": musica_ativo is not None, "arquivo": musica_arquivo.strip()},
            "intro": montagem_intro.strip(),
            "outro": montagem_outro.strip(),
        },
        "variacao": {
            "aberturas": variacao_aberturas,
            "estrutura": variacao_estrutura,
            "musica": variacao_musica,
            "estilo_visual": variacao_estilo_visual,
            "semente": semente,
        },
        "orcamento": {
            "por_video_usd": orcamento_por_video_usd,
            "por_dia_usd": orcamento_por_dia_usd,
            "acao": orcamento_acao,
        },
        "checkpoint": {"reaproveitar": checkpoint_reaproveitar is not None},
    }

    try:
        validado = GeracaoConfig(**dados)
    except ValidationError as e:
        return _render(id, request, dados, erro=_formatar_erros(e), status_code=422)

    tipo = carregar_tipo(id)
    completo = tipo.config.get_all()
    completo["geracao"] = validado.model_dump()
    tipo.config.salvar(completo)

    return _render(id, request, validado.model_dump(), sucesso=True)


@router.post("/reexecutar/{execucao_id}", response_class=HTMLResponse)
def reexecutar(id: str, execucao_id: str, request: Request):
    tipo = carregar_tipo(id)
    g = mesclar_geracao(tipo.config.get_all().get("geracao"))
    try:
        scheduler_mod.reexecutar_agora(execucao_id)
    except (ValueError, execucoes_mod.ExecucaoEmAndamentoError, KeyError) as e:
        return _render(id, request, g, erro=str(e), status_code=422)
    return _render(id, request, g, sucesso=True)
