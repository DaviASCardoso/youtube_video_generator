import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import SistemaConfig
from operacoes import notificacoes
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


def _campos_notif() -> list:
    return formulario.arvore(notificacoes.NOTIFICACOES_PADRAO, notificacoes.config(), notificacoes.UI_HINTS)


def _status_ntfy() -> dict:
    return {
        "configurado": notificacoes.configurado(),
        "servidor": notificacoes.servidor(),
        "topico": bool(notificacoes.topico()),
        "token": bool(os.getenv("NTFY_TOKEN")),
    }


def _ctx_notif(request: Request, erro=None, sucesso=False, msg=None) -> dict:
    return {
        "request": request,
        "campos_notif": _campos_notif(),
        "ntfy": _status_ntfy(),
        "erro_notif": erro,
        "sucesso_notif": sucesso,
        "msg_notif": msg,
    }


@router.get("", response_class=HTMLResponse)
def pagina_configuracoes(request: Request):
    return templates.TemplateResponse(
        "configuracoes.html",
        {"request": request, "campos": _campos(sistema.get_all()), "erro": None, "sucesso": False, **_ctx_notif(request)},
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

    # Preserva o bloco `notificacoes` (editado noutra seção) no whole-file replace.
    novo = validado.model_dump()
    atual = sistema.get_all()
    if "notificacoes" in atual:
        novo["notificacoes"] = atual["notificacoes"]
    sistema.salvar(novo)
    scheduler_mod.atualizar_max_simultaneo(validado.execucao.max_simultaneo)

    return templates.TemplateResponse(
        "_configuracoes_form.html",
        {"request": request, "campos": _campos(sistema.get_all()), "erro": None, "sucesso": True},
    )


@router.post("/notificacoes", response_class=HTMLResponse)
async def salvar_notificacoes(request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, notificacoes.NOTIFICACOES_PADRAO, notificacoes.UI_HINTS)
    completo = sistema.get_all()
    completo["notificacoes"] = notificacoes.mesclar_notificacoes(dados)
    sistema.salvar(completo)
    return templates.TemplateResponse("_notificacoes_form.html", _ctx_notif(request, sucesso=True))


@router.post("/notificacoes/teste", response_class=HTMLResponse)
def testar_notificacoes(request: Request):
    if notificacoes.enviar_teste():
        msg = "Notificação de teste enviada. Confira o app ntfy no seu telefone."
    else:
        msg = "Não foi possível enviar — verifique se NTFY_TOPIC está definido no .env."
    return templates.TemplateResponse("_notificacoes_form.html", _ctx_notif(request, msg=msg))
