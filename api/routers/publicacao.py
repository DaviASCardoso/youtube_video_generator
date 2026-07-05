from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api.schemas import PublicacaoConfig
from api.templating import templates
from config.constantes import VISIBILIDADES
from config.tipos import TipoVideo, carregar_tipo
from operacoes import execucoes as execucoes_mod
from operacoes import scheduler as scheduler_mod
from publicacao.configuracao import (
    ACOES_QUOTA,
    AUDIENCIAS,
    ESTRATEGIAS_TAGS,
    FONTES_FUNDO_THUMB,
    MODOS_REVISAO_PUB,
    MODOS_TIMING,
    POSICOES_TEXTO_THUMB,
    mesclar_publicacao,
)
from publicacao.destinos import base as destinos_base

router = APIRouter(prefix="/tipos/{id}/publicacao", tags=["publicacao"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _enums() -> dict:
    return {
        "modos_revisao": MODOS_REVISAO_PUB,
        "modos_timing": MODOS_TIMING,
        "privacidades": VISIBILIDADES,
        "audiencias": AUDIENCIAS,
        "estrategias_tags": ESTRATEGIAS_TAGS,
        "fontes_fundo": FONTES_FUNDO_THUMB,
        "posicoes_texto": POSICOES_TEXTO_THUMB,
        "acoes_quota": ACOES_QUOTA,
        "destinos_implementados": destinos_base.disponiveis(),
    }


def _runs_publicacao(tipo: TipoVideo) -> list[dict]:
    return execucoes_mod.historico.listar(tipo.id)[:8]


def contexto_publicacao(tipo: TipoVideo) -> dict:
    """Contexto para renderizar a aba Publicação (usado também na página de edição)."""
    return {
        "tipo": tipo,
        "p": mesclar_publicacao(tipo.config.get_all().get("publicacao")),
        "runs_publicacao": _runs_publicacao(tipo),
        "credencial": None,
        **_enums(),
    }


def _render(tipo_id, request, p, erro=None, sucesso=False, credencial=None, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "p": p,
        "runs_publicacao": _runs_publicacao(tipo),
        "credencial": credencial,
        "erro": erro,
        "sucesso": sucesso,
        **_enums(),
    }
    return templates.TemplateResponse("_tipos_publicacao_tab.html", ctx, status_code=status_code)


def _linhas_virgula(texto: str) -> list[str]:
    return [t.strip() for t in texto.split(",") if t.strip()]


@router.post("", response_class=HTMLResponse)
def salvar(
    id: str,
    request: Request,
    revisao: str = Form(...),
    timing_modo: str = Form(...),
    timing_horario: str = Form(...),
    timing_fuso_horario: str = Form(...),
    vis_privacidade: str = Form(...),
    vis_audiencia: str = Form(...),
    vis_disclosure: str | None = Form(None),
    meta_tom: str = Form(""),
    meta_template_titulo: str = Form(""),
    meta_template_descricao: str = Form(""),
    meta_estrategia_tags: str = Form(...),
    meta_max_tags: int = Form(...),
    thumb_ativo: str | None = Form(None),
    thumb_fonte_fundo: str = Form(...),
    thumb_fonte: str = Form(""),
    thumb_tamanho: int = Form(...),
    thumb_cor: str = Form(...),
    thumb_posicao: str = Form(...),
    thumb_contorno_cor: str = Form(...),
    thumb_contorno_largura: int = Form(...),
    quota_cap_diario: int = Form(...),
    quota_acao: str = Form(...),
    yt_ativo: str | None = Form(None),
    yt_categoria_id: str = Form(...),
    yt_idioma: str = Form(...),
    yt_playlist: str = Form(""),
    yt_tags_base: str = Form(""),
    yt_descricao_base: str = Form(""),
):
    dados = {
        "revisao": revisao,
        "timing": {"modo": timing_modo, "horario": timing_horario, "fuso_horario": timing_fuso_horario},
        "visibilidade": {
            "privacidade": vis_privacidade,
            "audiencia": vis_audiencia,
            "disclosure_sintetico": vis_disclosure is not None,
        },
        "metadados": {
            "tom": meta_tom.strip(),
            "template_titulo": meta_template_titulo.strip(),
            "template_descricao": meta_template_descricao.strip(),
            "estrategia_tags": meta_estrategia_tags,
            "max_tags": meta_max_tags,
        },
        "thumbnail": {
            "ativo": thumb_ativo is not None,
            "fonte_fundo": thumb_fonte_fundo,
            "texto": {
                "fonte": thumb_fonte.strip(),
                "tamanho": thumb_tamanho,
                "cor": thumb_cor.strip(),
                "posicao": thumb_posicao,
                "contorno_cor": thumb_contorno_cor.strip(),
                "contorno_largura": thumb_contorno_largura,
            },
        },
        "quota": {"cap_diario": quota_cap_diario, "acao": quota_acao},
        "destinos": {
            "youtube": {
                "ativo": yt_ativo is not None,
                "categoria_id": yt_categoria_id,
                "idioma": yt_idioma.strip(),
                "playlist": yt_playlist.strip(),
                "tags_base": _linhas_virgula(yt_tags_base),
                "descricao_base": yt_descricao_base.strip(),
            }
        },
    }

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
