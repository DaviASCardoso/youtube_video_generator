from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import DescobertaConfig
from api.templating import templates
from config.tipos import carregar_tipo, TipoVideo
from descoberta import estado
from descoberta.configuracao import DESCOBERTA_PADRAO, UI_HINTS, mesclar_descoberta
from operacoes import scheduler as scheduler_mod

router = APIRouter(prefix="/tipos/{id}/descoberta", tags=["descoberta"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _campos(atual: dict) -> list:
    return formulario.arvore(DESCOBERTA_PADRAO, atual, UI_HINTS)


def contexto_descoberta(tipo: TipoVideo) -> dict:
    """Contexto para renderizar a aba Descoberta (usado também na página de edição)."""
    atual = mesclar_descoberta(tipo.config.get_all().get("descoberta"))
    return {
        "tipo": tipo,
        "campos_descoberta": _campos(atual),
        "decisao": estado.slot_de(tipo).ler(),
        "runs": estado.historico_de(tipo).listar()[:8],
    }


def _render(tipo_id, request, atual, erro=None, sucesso=False, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "campos_descoberta": _campos(atual),
        "decisao": estado.slot_de(tipo).ler(),
        "runs": estado.historico_de(tipo).listar()[:8],
        "erro": erro,
        "sucesso": sucesso,
    }
    return templates.TemplateResponse("_tipos_descoberta_tab.html", ctx, status_code=status_code)


@router.post("", response_class=HTMLResponse)
async def salvar(id: str, request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, DESCOBERTA_PADRAO, UI_HINTS)

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
