"""Aba Conformidade do painel: config schema-driven + editor do conjunto de regras.

Duas responsabilidades, dois POSTs:

- `/tipos/{id}/conformidade` — salva o bloco `conformidade` (o *como* de cada checagem),
  schema-driven sobre `CONFORMIDADE_PADRAO` (mesmo padrão da aba Operação).
- `/tipos/{id}/conformidade/regras` — publica uma nova versão do **conjunto de regras**
  (o *conteúdo*: listas de brand safety, regra de disclosure, mapa de licenças), editado
  como JSON e versionado com uma nota no changelog (`conformidade/regras.py`).
"""

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import ConformidadeConfig
from api.templating import templates
from conformidade.configuracao import CONFORMIDADE_PADRAO, UI_HINTS, mesclar_conformidade
from conformidade.regras import regras_de
from config.tipos import TipoVideo, carregar_tipo

router = APIRouter(prefix="/tipos/{id}/conformidade", tags=["conformidade"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _campos(atual: dict) -> list:
    return formulario.arvore(CONFORMIDADE_PADRAO, atual, UI_HINTS)


def _estado_regras(tipo: TipoVideo) -> dict:
    estado = regras_de(tipo).estado()
    return {
        "regras_json": json.dumps(estado["regras"], ensure_ascii=False, indent=2),
        "regras_versao": estado["versao"],
        "regras_atualizado_em": estado["atualizado_em"],
        "regras_changelog": list(reversed(estado.get("changelog", []))),
    }


def contexto_conformidade(tipo: TipoVideo) -> dict:
    """Contexto da aba Conformidade (config + editor de regras), usado na edição."""
    atual = mesclar_conformidade(tipo.config.get_all().get("conformidade"))
    return {"tipo": tipo, "campos_conformidade": _campos(atual), **_estado_regras(tipo)}


def _render(tipo_id, request, atual, *, erro=None, sucesso=False,
            erro_regras=None, sucesso_regras=False, regras_json=None, status_code=200):
    tipo = carregar_tipo(tipo_id)
    estado = _estado_regras(tipo)
    if regras_json is not None:  # preserva a edição do usuário num erro de parse/publish
        estado["regras_json"] = regras_json
    ctx = {
        "request": request,
        "tipo": tipo,
        "campos_conformidade": _campos(atual),
        "erro": erro,
        "sucesso": sucesso,
        "erro_regras": erro_regras,
        "sucesso_regras": sucesso_regras,
        **estado,
    }
    return templates.TemplateResponse(
        "_tipos_conformidade_tab.html", ctx, status_code=status_code
    )


@router.post("", response_class=HTMLResponse)
async def salvar(id: str, request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, CONFORMIDADE_PADRAO, UI_HINTS)

    try:
        validado = ConformidadeConfig(**dados)
    except ValidationError as e:
        return _render(id, request, dados, erro=_formatar_erros(e), status_code=422)

    tipo = carregar_tipo(id)
    completo = tipo.config.get_all()
    completo["conformidade"] = validado.model_dump()
    tipo.config.salvar(completo)

    return _render(id, request, validado.model_dump(), sucesso=True)


@router.post("/regras", response_class=HTMLResponse)
async def publicar_regras(id: str, request: Request, regras: str = Form(""), nota: str = Form("")):
    tipo = carregar_tipo(id)
    atual = mesclar_conformidade(tipo.config.get_all().get("conformidade"))

    try:
        conteudo = json.loads(regras)
    except json.JSONDecodeError as e:
        return _render(
            id, request, atual, erro_regras=f"JSON inválido: {e}",
            regras_json=regras, status_code=422,
        )
    if not isinstance(conteudo, dict):
        return _render(
            id, request, atual, erro_regras="O conjunto de regras precisa ser um objeto JSON.",
            regras_json=regras, status_code=422,
        )

    regras_de(tipo).publicar(conteudo, nota.strip())
    return _render(id, request, atual, sucesso_regras=True)
