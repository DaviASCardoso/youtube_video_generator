from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from api.templating import templates
from config.constantes import FONTES_TEMA
from config.tipos import carregar_tipo, TipoVideo

router = APIRouter(prefix="/tipos/{id}/temas", tags=["temas"])


def contexto_temas(tipo: TipoVideo) -> dict:
    return {"tipo": tipo, "temas": tipo.temas.listar(), "fontes": FONTES_TEMA}


def _resposta(tipo_id: str, request: Request, erro: str | None = None, status_code: int = 200):
    tipo = carregar_tipo(tipo_id)
    return templates.TemplateResponse(
        "_tipos_temas_tab.html",
        {"request": request, **contexto_temas(tipo), "erro": erro},
        status_code=status_code,
    )


@router.post("", response_class=HTMLResponse)
def adicionar(id: str, request: Request, tema: str = Form(...), prioridade: int = Form(...), fonte: str = Form("manual")):
    tema = tema.strip()
    fonte = fonte.strip() or "manual"

    if not tema:
        return _resposta(id, request, erro="O tema não pode ficar vazio.", status_code=422)
    if not 0 <= prioridade <= 100:
        return _resposta(id, request, erro="Prioridade deve ser entre 0 e 100.", status_code=422)

    tipo = carregar_tipo(id)
    tipo.temas.adicionar(tema, prioridade, fonte)
    return _resposta(id, request)


@router.post("/{indice}/prioridade", response_class=HTMLResponse)
def alterar_prioridade(id: str, indice: int, request: Request, nova_prioridade: int = Form(...)):
    tipo = carregar_tipo(id)
    try:
        tipo.temas.alterar_prioridade(indice, nova_prioridade)
    except (IndexError, ValueError) as e:
        return _resposta(id, request, erro=str(e), status_code=422)
    return _resposta(id, request)


@router.delete("/{indice}", response_class=HTMLResponse)
def remover(id: str, indice: int, request: Request):
    tipo = carregar_tipo(id)
    try:
        tipo.temas.remover(indice)
    except IndexError as e:
        return _resposta(id, request, erro=str(e), status_code=422)
    return _resposta(id, request)


@router.delete("", response_class=HTMLResponse)
def limpar(id: str, request: Request):
    tipo = carregar_tipo(id)
    tipo.temas.limpar()
    return _resposta(id, request)
