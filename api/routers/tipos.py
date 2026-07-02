from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from api.schemas import TipoConfig
from api.templating import templates
from api import scheduler as scheduler_mod
from config.constantes import FREQUENCIAS, VISIBILIDADES
from config.tipos import (
    carregar_tipo,
    listar_tipos,
    criar_tipo,
    duplicar_tipo,
    renomear_tipo,
    excluir_tipo,
)
from scripts.execucoes import historico
from scripts.generate_image import ASPECT_RATIOS
from api.routers.assets import contexto_prompts
from api.routers.temas import contexto_temas

router = APIRouter(prefix="/tipos", tags=["tipos"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _proxima_execucao(tipo):
    if not tipo.ativo:
        return None
    job = scheduler_mod.scheduler.get_job(tipo.id)
    return job.next_run_time if job else None


def _linhas():
    return [{"tipo": t, "proxima_execucao": _proxima_execucao(t)} for t in listar_tipos()]


@router.get("", response_class=HTMLResponse)
def pagina_lista(request: Request):
    return templates.TemplateResponse(
        "tipos_lista.html", {"request": request, "linhas": _linhas(), "erro": None}
    )


@router.post("/{id}/toggle-ativo", response_class=HTMLResponse)
def alternar_ativo(id: str, request: Request):
    tipo = carregar_tipo(id)
    dados = tipo.config.get_all()
    dados["ativo"] = not tipo.ativo
    tipo.config.salvar(dados)

    tipo = carregar_tipo(id)
    if tipo.ativo:
        scheduler_mod.registrar_job(tipo)
    else:
        scheduler_mod.remover_job(id)

    return templates.TemplateResponse(
        "_tipos_lista_partial.html", {"request": request, "linhas": _linhas(), "erro": None}
    )


@router.get("/novo", response_class=HTMLResponse)
def pagina_novo(request: Request):
    return templates.TemplateResponse("tipos_novo.html", {"request": request, "erro": None})


@router.post("/novo")
def criar(nome: str = Form(...)):
    nome = nome.strip()
    tipo = criar_tipo(nome)
    return RedirectResponse(url=f"/tipos/{tipo.id}/editar", status_code=303)


@router.post("/{id}/duplicar")
def duplicar(id: str, novo_nome: str = Form(...)):
    novo_nome = novo_nome.strip() or f"{carregar_tipo(id).nome} (cópia)"
    novo = duplicar_tipo(id, novo_nome)
    return RedirectResponse(url=f"/tipos/{novo.id}/editar", status_code=303)


@router.post("/{id}/renomear")
def renomear(id: str, novo_nome: str = Form(...)):
    novo_nome = novo_nome.strip()
    if not novo_nome:
        return RedirectResponse(url=f"/tipos/{id}/editar", status_code=303)

    tipo = renomear_tipo(id, novo_nome)
    scheduler_mod.reagendar_job(id, tipo)
    historico.migrar_tipo_id(id, tipo.id)
    return RedirectResponse(url=f"/tipos/{tipo.id}/editar", status_code=303)


@router.delete("/{id}", response_class=HTMLResponse)
def excluir(id: str, request: Request):
    if historico.em_execucao(id):
        return templates.TemplateResponse(
            "_tipos_lista_partial.html",
            {
                "request": request,
                "linhas": _linhas(),
                "erro": f"Não é possível excluir '{id}': há uma execução em andamento para esse tipo.",
            },
            status_code=409,
        )

    scheduler_mod.remover_job(id)
    excluir_tipo(id)
    return templates.TemplateResponse(
        "_tipos_lista_partial.html", {"request": request, "linhas": _linhas(), "erro": None}
    )


@router.get("/{id}/editar", response_class=HTMLResponse)
def pagina_editar(id: str, request: Request):
    tipo = carregar_tipo(id)
    return templates.TemplateResponse(
        "tipos_editar.html",
        {
            "request": request,
            "tipo": tipo,
            "config": tipo.config.get_all(),
            "erro": None,
            "sucesso": False,
            "aspect_ratios": list(ASPECT_RATIOS),
            "frequencias": FREQUENCIAS,
            "visibilidades": VISIBILIDADES,
            **contexto_prompts(tipo),
            **contexto_temas(tipo),
        },
    )


@router.post("/{id}/config", response_class=HTMLResponse)
def salvar_config(
    id: str,
    request: Request,
    nome: str = Form(...),
    ativo: str | None = Form(None),
    groq_modelo: str = Form(...),
    groq_temperatura: float = Form(...),
    groq_max_tokens: int = Form(...),
    together_modelo: str = Form(...),
    together_steps: int = Form(...),
    together_aspect_ratio: str = Form(...),
    tts_idioma: str = Form(...),
    tts_voz: str = Form(...),
    tts_velocidade: float = Form(...),
    tts_pitch: float = Form(...),
    pipeline_min_chars_por_periodo: int = Form(...),
    agendamento_frequencia: str = Form(...),
    agendamento_horario: str = Form(...),
    agendamento_fuso_horario: str = Form(...),
    youtube_categoria_id: str = Form(...),
    youtube_visibilidade: str = Form(...),
    youtube_tags: str = Form(""),
):
    dados = {
        "nome": nome.strip(),
        "ativo": ativo is not None,
        "groq": {
            "modelo": groq_modelo,
            "temperatura": groq_temperatura,
            "max_tokens": groq_max_tokens,
        },
        "together": {
            "modelo": together_modelo,
            "steps": together_steps,
            "aspect_ratio": together_aspect_ratio,
        },
        "tts": {
            "idioma": tts_idioma,
            "voz": tts_voz,
            "velocidade": tts_velocidade,
            "pitch": tts_pitch,
        },
        "pipeline": {"min_chars_por_periodo": pipeline_min_chars_por_periodo},
        "agendamento": {
            "frequencia": agendamento_frequencia,
            "horario": agendamento_horario,
            "fuso_horario": agendamento_fuso_horario,
        },
        "youtube": {
            "categoria_id": youtube_categoria_id,
            "visibilidade": youtube_visibilidade,
            "tags": [t.strip() for t in youtube_tags.split(",") if t.strip()],
        },
    }

    tipo_atual = carregar_tipo(id)
    contexto_base = {
        "request": request,
        "tipo": tipo_atual,
        "aspect_ratios": list(ASPECT_RATIOS),
        "frequencias": FREQUENCIAS,
        "visibilidades": VISIBILIDADES,
    }

    try:
        validado = TipoConfig(**dados)
    except ValidationError as e:
        return templates.TemplateResponse(
            "_tipos_config_tab.html",
            {**contexto_base, "config": dados, "erro": _formatar_erros(e), "sucesso": False},
            status_code=422,
        )

    tipo_atual.config.salvar(validado.model_dump())
    tipo = carregar_tipo(id)

    if tipo.ativo:
        scheduler_mod.registrar_job(tipo)
    else:
        scheduler_mod.remover_job(id)

    return templates.TemplateResponse(
        "_tipos_config_tab.html",
        {**contexto_base, "tipo": tipo, "config": tipo.config.get_all(), "erro": None, "sucesso": True},
    )
