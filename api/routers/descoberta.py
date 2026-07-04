from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api.schemas import DescobertaConfig
from api.templating import templates
from config.constantes import FEEDS_TRENDS
from config.tipos import carregar_tipo, TipoVideo
from descoberta import estado
from descoberta.configuracao import (
    ESTRATEGIAS_DEDUP,
    MODOS_REVIEW,
    POLITICAS_RETENCAO,
    REDDIT_PERIODOS,
    mesclar_descoberta,
)
from operacoes import scheduler as scheduler_mod

router = APIRouter(prefix="/tipos/{id}/descoberta", tags=["descoberta"])


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def contexto_descoberta(tipo: TipoVideo) -> dict:
    """Contexto para renderizar a aba Descoberta (usado também na página de edição)."""
    return {
        "tipo": tipo,
        "d": mesclar_descoberta(tipo.config.get_all().get("descoberta")),
        "feeds": FEEDS_TRENDS,
        "estrategias": ESTRATEGIAS_DEDUP,
        "modos_revisao": MODOS_REVIEW,
        "retencoes": POLITICAS_RETENCAO,
        "periodos_reddit": REDDIT_PERIODOS,
        "decisao": estado.slot_de(tipo).ler(),
        "runs": estado.historico_de(tipo).listar()[:8],
    }


def _render(tipo_id, request, d, erro=None, sucesso=False, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "d": d,
        "feeds": FEEDS_TRENDS,
        "estrategias": ESTRATEGIAS_DEDUP,
        "modos_revisao": MODOS_REVIEW,
        "retencoes": POLITICAS_RETENCAO,
        "periodos_reddit": REDDIT_PERIODOS,
        "decisao": estado.slot_de(tipo).ler(),
        "runs": estado.historico_de(tipo).listar()[:8],
        "erro": erro,
        "sucesso": sucesso,
    }
    return templates.TemplateResponse("_tipos_descoberta_tab.html", ctx, status_code=status_code)


@router.post("", response_class=HTMLResponse)
def salvar(
    id: str,
    request: Request,
    antecedencia_horas: int = Form(...),
    f_trends_mcp_ativo: str | None = Form(None),
    f_trends_mcp_feed: str = Form(...),
    f_trends_mcp_limite: int = Form(...),
    f_youtube_ativo: str | None = Form(None),
    f_youtube_limite: int = Form(...),
    f_youtube_consultas: str = Form(""),
    f_youtube_canais: str = Form(""),
    f_youtube_regiao: str = Form(...),
    f_google_trends_ativo: str | None = Form(None),
    f_google_trends_limite: int = Form(...),
    f_google_trends_geo: str = Form(...),
    f_reddit_ativo: str | None = Form(None),
    f_reddit_subreddits: str = Form(""),
    f_reddit_limite: int = Form(...),
    f_reddit_periodo: str = Form(...),
    f_wikipedia_ativo: str | None = Form(None),
    f_wikipedia_limite: int = Form(...),
    f_manual_ativo: str | None = Form(None),
    f_evergreen_ativo: str | None = Form(None),
    fit_score_minimo: int = Form(...),
    dedup_dias: int = Form(...),
    dedup_estrategia: str = Form(...),
    dedup_limiar: float = Form(...),
    sel_peso_sinal: float = Form(...),
    sel_peso_fit: float = Form(...),
    sel_peso_frescor: float = Form(...),
    sel_meia_vida_horas: float = Form(...),
    evergreen_ratio: float = Form(...),
    modo_revisao: str = Form(...),
    retencao: str = Form(...),
    orcamento_avaliacao: int = Form(...),
):
    dados = {
        "antecedencia_horas": antecedencia_horas,
        "fontes": {
            "trends_mcp": {
                "ativo": f_trends_mcp_ativo is not None,
                "feed": f_trends_mcp_feed,
                "limite": f_trends_mcp_limite,
            },
            "youtube": {
                "ativo": f_youtube_ativo is not None,
                "limite": f_youtube_limite,
                "consultas": _linhas(f_youtube_consultas),
                "canais_nicho": _linhas(f_youtube_canais),
                "regiao": f_youtube_regiao.strip().upper(),
            },
            "google_trends": {
                "ativo": f_google_trends_ativo is not None,
                "limite": f_google_trends_limite,
                "geo": f_google_trends_geo.strip().upper(),
            },
            "reddit": {
                "ativo": f_reddit_ativo is not None,
                "subreddits": _linhas(f_reddit_subreddits),
                "limite": f_reddit_limite,
                "periodo": f_reddit_periodo,
            },
            "wikipedia": {
                "ativo": f_wikipedia_ativo is not None,
                "limite": f_wikipedia_limite,
            },
            "manual": {"ativo": f_manual_ativo is not None},
            "evergreen": {"ativo": f_evergreen_ativo is not None},
        },
        "fit": {"score_minimo": fit_score_minimo},
        "dedup": {"dias": dedup_dias, "estrategia": dedup_estrategia, "limiar": dedup_limiar},
        "selecao": {
            "peso_sinal": sel_peso_sinal,
            "peso_fit": sel_peso_fit,
            "peso_frescor": sel_peso_frescor,
            "meia_vida_horas": sel_meia_vida_horas,
        },
        "evergreen_ratio": evergreen_ratio,
        "modo_revisao": modo_revisao,
        "retencao": retencao,
        "orcamento_avaliacao": orcamento_avaliacao,
    }

    try:
        validado = DescobertaConfig(**dados)
    except ValidationError as e:
        return _render(id, request, dados, erro=_formatar_erros(e), status_code=422)

    tipo = carregar_tipo(id)
    completo = tipo.config.get_all()
    completo["descoberta"] = validado.model_dump()
    tipo.config.salvar(completo)

    tipo = carregar_tipo(id)
    # antecedencia_horas mudou o horário do job de descoberta → reagenda.
    if tipo.ativo:
        scheduler_mod.registrar_job(tipo)

    return _render(id, request, validado.model_dump(), sucesso=True)


@router.post("/aprovar", response_class=HTMLResponse)
def aprovar(id: str, request: Request):
    tipo = carregar_tipo(id)
    estado.slot_de(tipo).aprovar()
    return _render(id, request, mesclar_descoberta(tipo.config.get_all().get("descoberta")))


@router.post("/rejeitar", response_class=HTMLResponse)
def rejeitar(id: str, request: Request):
    tipo = carregar_tipo(id)
    estado.slot_de(tipo).limpar()
    return _render(id, request, mesclar_descoberta(tipo.config.get_all().get("descoberta")))
