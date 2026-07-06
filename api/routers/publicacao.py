from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import PublicacaoConfig
from api.templating import templates
from config.tipos import TipoVideo, carregar_tipo
from operacoes import execucoes as execucoes_mod
from operacoes import scheduler as scheduler_mod
from publicacao.configuracao import PUBLICACAO_PADRAO, UI_HINTS, mesclar_publicacao
from publicacao.destinos import base as destinos_base

router = APIRouter(prefix="/tipos/{id}/publicacao", tags=["publicacao"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _campos(atual: dict) -> list:
    return formulario.arvore(PUBLICACAO_PADRAO, atual, UI_HINTS)


def _runs_publicacao(tipo: TipoVideo) -> list[dict]:
    return execucoes_mod.historico.listar(tipo.id)[:8]


def contexto_publicacao(tipo: TipoVideo) -> dict:
    """Contexto para renderizar a aba Publicação (usado também na página de edição)."""
    atual = mesclar_publicacao(tipo.config.get_all().get("publicacao"))
    return {
        "tipo": tipo,
        "campos_publicacao": _campos(atual),
        "runs_publicacao": _runs_publicacao(tipo),
        "credencial": None,
    }


def _render(tipo_id, request, atual, erro=None, sucesso=False, credencial=None, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "campos_publicacao": _campos(atual),
        "runs_publicacao": _runs_publicacao(tipo),
        "credencial": credencial,
        "erro": erro,
        "sucesso": sucesso,
    }
    return templates.TemplateResponse("_tipos_publicacao_tab.html", ctx, status_code=status_code)


@router.post("", response_class=HTMLResponse)
async def salvar(id: str, request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, PUBLICACAO_PADRAO, UI_HINTS)

    try:
        validado = PublicacaoConfig(**dados)
    except ValidationError as e:
        return _render(id, request, dados, erro=_formatar_erros(e), status_code=422)

    tipo = carregar_tipo(id)
    completo = tipo.config.get_all()
    completo["publicacao"] = validado.model_dump()
    tipo.config.salvar(completo)

    return _render(id, request, validado.model_dump(), sucesso=True)


@router.post("/publicar/{execucao_id}", response_class=HTMLResponse)
def publicar(id: str, execucao_id: str, request: Request):
    """Aprova & publica (gate de revisão) ou reconcilia/republica após falha parcial —
    ambos disparam a mesma ação idempotente em background."""
    tipo = carregar_tipo(id)
    p = mesclar_publicacao(tipo.config.get_all().get("publicacao"))
    try:
        scheduler_mod.publicar_agora(execucao_id)
    except Exception as e:  # noqa: BLE001
        return _render(id, request, p, erro=str(e), status_code=422)
    return _render(id, request, p, sucesso=True)


@router.post("/credencial/{destino}", response_class=HTMLResponse)
def verificar_credencial(id: str, destino: str, request: Request):
    """Verificação não-destrutiva da credencial de um destino (surfaca token expirado)."""
    tipo = carregar_tipo(id)
    p = mesclar_publicacao(tipo.config.get_all().get("publicacao"))
    try:
        cred = destinos_base.obter(destino).checar_credencial(tipo)
        cred = {"destino": destino, **cred}
    except Exception as e:  # noqa: BLE001
        cred = {"destino": destino, "status": "erro", "detalhe": str(e)}
    return _render(id, request, p, credencial=cred)
