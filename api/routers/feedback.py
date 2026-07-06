from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import FeedbackConfig
from api.templating import templates
from config.tipos import TipoVideo, carregar_tipo
from feedback.configuracao import FEEDBACK_PADRAO, UI_HINTS, mesclar_feedback

router = APIRouter(prefix="/tipos/{id}/feedback", tags=["feedback"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _campos(atual: dict) -> list:
    return formulario.arvore(FEEDBACK_PADRAO, atual, UI_HINTS)


def contexto_feedback(tipo: TipoVideo) -> dict:
    """Contexto da aba Feedback (config schema-driven), usado na página de edição."""
    atual = mesclar_feedback(tipo.config.get_all().get("feedback"))
    return {"tipo": tipo, "campos_feedback": _campos(atual)}


def _render(tipo_id, request, atual, erro=None, sucesso=False, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "campos_feedback": _campos(atual),
        "erro": erro,
        "sucesso": sucesso,
    }
    return templates.TemplateResponse("_tipos_feedback_tab.html", ctx, status_code=status_code)


@router.post("", response_class=HTMLResponse)
async def salvar(id: str, request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, FEEDBACK_PADRAO, UI_HINTS)

    try:
        validado = FeedbackConfig(**dados)
    except ValidationError as e:
        return _render(id, request, dados, erro=_formatar_erros(e), status_code=422)

    tipo = carregar_tipo(id)
    completo = tipo.config.get_all()
    completo["feedback"] = validado.model_dump()
    tipo.config.salvar(completo)

    return _render(id, request, validado.model_dump(), sucesso=True)
