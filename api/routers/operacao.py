from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import OperacaoConfig
from api.templating import templates
from config.tipos import TipoVideo, carregar_tipo
from operacoes.configuracao import OPERACAO_PADRAO, UI_HINTS, mesclar_operacao

router = APIRouter(prefix="/tipos/{id}/operacao", tags=["operacao"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _campos(atual: dict) -> list:
    return formulario.arvore(OPERACAO_PADRAO, atual, UI_HINTS)


def contexto_operacao(tipo: TipoVideo) -> dict:
    """Contexto da aba Operação (config schema-driven), usado na página de edição."""
    atual = mesclar_operacao(tipo.config.get_all().get("operacao"))
    return {"tipo": tipo, "campos_operacao": _campos(atual)}


def _render(tipo_id, request, atual, erro=None, sucesso=False, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "campos_operacao": _campos(atual),
        "erro": erro,
        "sucesso": sucesso,
    }
    return templates.TemplateResponse("_tipos_operacao_tab.html", ctx, status_code=status_code)


@router.post("", response_class=HTMLResponse)
async def salvar(id: str, request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, OPERACAO_PADRAO, UI_HINTS)

    try:
        validado = OperacaoConfig(**dados)
    except ValidationError as e:
        return _render(id, request, dados, erro=_formatar_erros(e), status_code=422)

    tipo = carregar_tipo(id)
    completo = tipo.config.get_all()
    completo["operacao"] = validado.model_dump()
    tipo.config.salvar(completo)

    # O enablement de job (operacao.jobs.*) muda o que o scheduler agenda — re-registra.
    from operacoes import scheduler as scheduler_mod

    tipo = carregar_tipo(id)
    if tipo.ativo:
        try:
            scheduler_mod.registrar_job(tipo)
        except Exception:  # noqa: BLE001 (scheduler pode não estar de pé em dev/testes)
            pass

    return _render(id, request, validado.model_dump(), sucesso=True)
