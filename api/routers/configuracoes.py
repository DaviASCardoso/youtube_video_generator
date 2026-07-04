from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from api.schemas import SistemaConfig
from operacoes import scheduler as scheduler_mod
from api.templating import templates
from config.constantes import FEEDS_TRENDS
from config.sistema import sistema

router = APIRouter(prefix="/configuracoes", tags=["configuracoes"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


@router.get("", response_class=HTMLResponse)
def pagina_configuracoes(request: Request):
    return templates.TemplateResponse(
        "configuracoes.html",
        {
            "request": request,
            "config": sistema.get_all(),
            "feeds": FEEDS_TRENDS,
            "erro": None,
            "sucesso": False,
        },
    )


@router.post("", response_class=HTMLResponse)
def salvar_configuracoes(
    request: Request,
    execucao_max_simultaneo: int = Form(...),
    saida_pasta_base: str = Form(...),
    video_fps: int = Form(...),
    video_codec: str = Form(...),
    video_audio_codec: str = Form(...),
    tendencias_ativo: str | None = Form(None),
    tendencias_horario: str = Form(...),
    tendencias_fuso_horario: str = Form(...),
    tendencias_feed: str = Form(...),
    tendencias_prioridade: int = Form(...),
    tendencias_limite: int = Form(...),
    tendencias_dias_historico: int = Form(...),
):
    dados = {
        "execucao": {"max_simultaneo": execucao_max_simultaneo},
        "saida": {"pasta_base": saida_pasta_base},
        "video": {"fps": video_fps, "codec": video_codec, "audio_codec": video_audio_codec},
        "tendencias": {
            "ativo": tendencias_ativo is not None,
            "horario": tendencias_horario,
            "fuso_horario": tendencias_fuso_horario,
            "feed": tendencias_feed,
            "prioridade": tendencias_prioridade,
            "limite": tendencias_limite,
            "dias_historico": tendencias_dias_historico,
        },
    }

    try:
        validado = SistemaConfig(**dados)
    except ValidationError as e:
        return templates.TemplateResponse(
            "_configuracoes_form.html",
            {
                "request": request,
                "config": dados,
                "feeds": FEEDS_TRENDS,
                "erro": _formatar_erros(e),
                "sucesso": False,
            },
            status_code=422,
        )

    sistema.salvar(validado.model_dump())
    scheduler_mod.atualizar_max_simultaneo(validado.execucao.max_simultaneo)
    scheduler_mod.registrar_job_tendencias()

    return templates.TemplateResponse(
        "_configuracoes_form.html",
        {
            "request": request,
            "config": sistema.get_all(),
            "feeds": FEEDS_TRENDS,
            "erro": None,
            "sucesso": True,
        },
    )
