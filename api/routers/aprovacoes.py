"""Gate de revisão & aprovação unificado.

Junta numa só tela os dois pontos onde o sistema espera por um humano: o tema
`pendente` da Descoberta (modo revisar) e o run `aguardando_publicacao` da Publicação
(gate de revisão). As ações delegam às operações que já existem nos pilares — Control
não decide nada, só relê os records e aciona aprovar/rejeitar/editar.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from api.templating import templates
from config.tipos import carregar_tipo, listar_tipos
from descoberta import estado
from operacoes import scheduler as scheduler_mod
from operacoes.execucoes import historico

router = APIRouter(prefix="/aprovacoes", tags=["aprovacoes"])


def _pendencias() -> dict:
    descoberta = []
    for tipo in listar_tipos():
        decisao = estado.slot_de(tipo).ler()
        if decisao is not None and decisao.estado == "pendente":
            descoberta.append({"tipo": tipo, "decisao": decisao})
    publicacao = [r for r in historico.listar() if r["status"] == "aguardando_publicacao"]
    return {"descoberta": descoberta, "publicacao": publicacao}


def _lista(request: Request, erro: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        "_aprovacoes_lista.html",
        {"request": request, **_pendencias(), "erro": erro},
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def pagina(request: Request):
    return templates.TemplateResponse(
        "aprovacoes.html", {"request": request, **_pendencias(), "erro": None}
    )


# --- Descoberta: tema pendente ----------------------------------------------


@router.post("/descoberta/{id}/aprovar", response_class=HTMLResponse)
def descoberta_aprovar(id: str, request: Request):
    estado.slot_de(carregar_tipo(id)).aprovar()
    return _lista(request)


@router.post("/descoberta/{id}/rejeitar", response_class=HTMLResponse)
def descoberta_rejeitar(id: str, request: Request):
    estado.slot_de(carregar_tipo(id)).limpar()
    return _lista(request)


@router.post("/descoberta/{id}/editar", response_class=HTMLResponse)
def descoberta_editar(id: str, request: Request, tema: str = Form(...)):
    tema = tema.strip()
    if tema:
        estado.slot_de(carregar_tipo(id)).editar_tema(tema)
    return _lista(request)


# --- Publicação: run aguardando aprovação -----------------------------------


@router.post("/publicacao/{execucao_id}/aprovar", response_class=HTMLResponse)
def publicacao_aprovar(execucao_id: str, request: Request):
    try:
        scheduler_mod.publicar_agora(execucao_id)
    except Exception as e:  # noqa: BLE001
        return _lista(request, erro=str(e), status_code=422)
    return _lista(request)


@router.post("/publicacao/{execucao_id}/rejeitar", response_class=HTMLResponse)
def publicacao_rejeitar(execucao_id: str, request: Request):
    historico.rejeitar_publicacao(execucao_id)
    return _lista(request)
