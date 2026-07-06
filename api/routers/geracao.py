from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import GeracaoConfig
from api.templating import templates
from config.tipos import TipoVideo, carregar_tipo
from geracao.configuracao import GERACAO_PADRAO, UI_HINTS, mesclar_geracao
from operacoes import execucoes as execucoes_mod
from operacoes import scheduler as scheduler_mod

router = APIRouter(prefix="/tipos/{id}/geracao", tags=["geracao"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _campos(atual: dict) -> list:
    return formulario.arvore(GERACAO_PADRAO, atual, UI_HINTS)


def _runs_geracao(tipo: TipoVideo) -> list[dict]:
    """Últimas execuções do tipo, para a observabilidade de custo/provedor."""
    return execucoes_mod.historico.listar(tipo.id)[:8]


def contexto_geracao(tipo: TipoVideo) -> dict:
    """Contexto para renderizar a aba Geração (usado também na página de edição)."""
    atual = mesclar_geracao(tipo.config.get_all().get("geracao"))
    return {
        "tipo": tipo,
        "campos_geracao": _campos(atual),
        "runs_geracao": _runs_geracao(tipo),
    }


def _render(tipo_id, request, atual, erro=None, sucesso=False, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "campos_geracao": _campos(atual),
        "runs_geracao": _runs_geracao(tipo),
        "erro": erro,
        "sucesso": sucesso,
    }
    return templates.TemplateResponse("_tipos_geracao_tab.html", ctx, status_code=status_code)


@router.post("", response_class=HTMLResponse)
async def salvar(id: str, request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, GERACAO_PADRAO, UI_HINTS)

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
