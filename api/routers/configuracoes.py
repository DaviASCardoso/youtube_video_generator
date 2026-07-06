from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import SistemaConfig
from operacoes import scheduler as scheduler_mod
from api.templating import templates
from config.sistema import sistema, SISTEMA_PADRAO, UI_HINTS

router = APIRouter(prefix="/configuracoes", tags=["configuracoes"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _campos(atual: dict) -> list:
    return formulario.arvore(SISTEMA_PADRAO, atual, UI_HINTS)


@router.get("", response_class=HTMLResponse)
def pagina_configuracoes(request: Request):
    return templates.TemplateResponse(
        "configuracoes.html",
        {"request": request, "campos": _campos(sistema.get_all()), "erro": None, "sucesso": False},
    )


@router.post("", response_class=HTMLResponse)
async def salvar_configuracoes(request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, SISTEMA_PADRAO, UI_HINTS)

    try:
        validado = SistemaConfig(**dados)
    except ValidationError as e:
        return templates.TemplateResponse(
            "_configuracoes_form.html",
            {"request": request, "campos": _campos(dados), "erro": _formatar_erros(e), "sucesso": False},
            status_code=422,
        )

    sistema.salvar(validado.model_dump())
    scheduler_mod.atualizar_max_simultaneo(validado.execucao.max_simultaneo)

    return templates.TemplateResponse(
        "_configuracoes_form.html",
        {"request": request, "campos": _campos(sistema.get_all()), "erro": None, "sucesso": True},
    )
