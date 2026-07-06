from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import TipoConfig
from api.templating import templates
from descoberta.configuracao import mesclar_descoberta
from feedback.configuracao import mesclar_feedback
from geracao.configuracao import mesclar_geracao
from publicacao.configuracao import mesclar_publicacao
from operacoes import scheduler as scheduler_mod
from config.constantes import FREQUENCIAS, MODOS_IMAGEM, VISIBILIDADES
from config.tipos import (
    DEFAULT_CONFIG,
    carregar_tipo,
    listar_tipos,
    criar_tipo,
    duplicar_tipo,
    renomear_tipo,
    excluir_tipo,
)
from geracao.compositor import POSICOES
from operacoes.execucoes import historico
from geracao.generate_image import ASPECT_RATIOS
from api.routers.assets import contexto_prompts
from api.routers.descoberta import contexto_descoberta
from api.routers.geracao import contexto_geracao
from api.routers.publicacao import contexto_publicacao
from api.routers.feedback import contexto_feedback
from api.routers.temas import contexto_temas

router = APIRouter(prefix="/tipos", tags=["tipos"])

# A aba Config edita nome/ativo + os blocos não-pilar do config.json. Os blocos de
# pilar (descoberta/geracao/publicacao) têm abas próprias e são preservados no salvar.
_BLOCOS_PILAR = ("descoberta", "geracao", "publicacao", "feedback")
CONFIG_TAB_PADRAO = {
    "nome": "",
    "ativo": False,
    **{k: v for k, v in DEFAULT_CONFIG.items() if k not in _BLOCOS_PILAR},
}

UI_HINTS_CONFIG = {
    "nome": {"rotulo": "Nome"},
    "ativo": {"rotulo": "Ativo (aparece no agendador)"},
    "groq": {"rotulo": "Roteiro (Groq)"},
    "groq.modelo": {"rotulo": "Modelo"},
    "groq.temperatura": {"rotulo": "Temperatura (0.0–2.0)", "min": 0, "max": 2, "passo": "0.1"},
    "groq.max_tokens": {"rotulo": "Máx. tokens", "min": 1, "max": 32768},
    "together": {"rotulo": 'Imagens por IA (Together — usado só no modo "ia")'},
    "together.modelo": {"rotulo": "Modelo"},
    "together.steps": {"rotulo": "Steps (1–50)", "min": 1, "max": 50},
    "together.aspect_ratio": {"rotulo": "Proporção", "opcoes": list(ASPECT_RATIOS)},
    "imagens": {"rotulo": "Cenas do vídeo"},
    "imagens.modo": {
        "rotulo": "Modo de geração", "opcoes": MODOS_IMAGEM,
        "rotulos_opcoes": {
            "ia": "ia — imagens geradas por IA (Together)",
            "personagem": "personagem — foto do Pexels + PNG do personagem",
        },
    },
    "imagens.largura": {"rotulo": "Largura do vídeo (px)", "min": 480, "max": 3840},
    "imagens.altura": {"rotulo": "Altura do vídeo (px)", "min": 480, "max": 3840},
    "imagens.personagem": {
        "rotulo": 'Personagem (modo "personagem")',
        "ajuda": "Os PNGs do personagem (um por emoção) ficam na aba Prompts. O canto inferior esquerdo é o único que a interface do YouTube Shorts deixa livre (direita = botões, baixo = título).",
    },
    "imagens.personagem.posicao": {
        "rotulo": "Posição na tela", "opcoes": POSICOES,
        "rotulos_opcoes": {p: p.replace("_", " ") for p in POSICOES},
    },
    "imagens.personagem.altura_percentual": {"rotulo": "Altura do personagem (% da tela, 10–100)", "min": 10, "max": 100},
    "imagens.personagem.margem_lateral": {"rotulo": "Margem lateral (px, distância da borda esquerda/direita)", "min": 0, "max": 1000},
    "imagens.personagem.margem_vertical": {"rotulo": "Margem vertical (px — deixe ~380 embaixo para o título do Shorts)", "min": 0, "max": 1000},
    "tts": {"rotulo": "Narração (Google TTS)"},
    "tts.idioma": {"rotulo": "Idioma (ex: pt-BR)"},
    "tts.voz": {"rotulo": "Voz"},
    "tts.velocidade": {"rotulo": "Velocidade (0.25–4.0)", "min": 0.25, "max": 4.0, "passo": "0.05"},
    "tts.pitch": {"rotulo": "Tom / pitch (-20.0–20.0)", "min": -20, "max": 20, "passo": "0.5"},
    "pipeline": {"rotulo": "Roteirização"},
    "pipeline.min_chars_por_periodo": {"rotulo": "Mínimo de caracteres por período", "min": 1},
    "agendamento": {"rotulo": "Agendamento"},
    "agendamento.frequencia": {"rotulo": "Frequência", "opcoes": FREQUENCIAS},
    "agendamento.horario": {"rotulo": "Horário (HH:MM)", "tipo": "time"},
    "agendamento.fuso_horario": {"rotulo": "Fuso horário (ex: America/Sao_Paulo)"},
    "youtube": {
        "rotulo": "YouTube (legado — a publicação agora é na aba Publicação)",
        "ajuda": "⚠️ Deixe o publicar desligado até ter certeza. A publicação real é configurada na aba Publicação (destino YouTube).",
    },
    "youtube.categoria_id": {"rotulo": "Id da categoria"},
    "youtube.visibilidade": {"rotulo": "Visibilidade", "opcoes": VISIBILIDADES},
    "youtube.tags": {"rotulo": "Tags (uma por linha)"},
    "youtube.publicar": {"rotulo": "Publicar automaticamente no YouTube após gerar (legado)"},
    "youtube.descricao_base": {"rotulo": "Descrição base (entra na descrição do vídeo, depois do roteiro)", "multilinha": True},
}


def _campos_config(atual: dict) -> list:
    return formulario.arvore(CONFIG_TAB_PADRAO, atual, UI_HINTS_CONFIG)


def contexto_config(tipo) -> dict:
    """Contexto da aba Config (campos schema-driven), usado na página de edição."""
    return {"campos_config": _campos_config(tipo.config.get_all())}


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
            "erro": None,
            "sucesso": False,
            **contexto_config(tipo),
            **contexto_prompts(tipo),
            **contexto_descoberta(tipo),
            **contexto_geracao(tipo),
            **contexto_publicacao(tipo),
            **contexto_feedback(tipo),
            **contexto_temas(tipo),
        },
    )


@router.post("/{id}/config", response_class=HTMLResponse)
async def salvar_config(id: str, request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, CONFIG_TAB_PADRAO, UI_HINTS_CONFIG)
    dados["nome"] = dados["nome"].strip()

    tipo_atual = carregar_tipo(id)
    # Preserva os blocos editados noutras abas (Descoberta, Geração, Publicação): esta
    # aba faz whole-file replace do config.json e os apagaria sem isto.
    atual = tipo_atual.config.get_all()
    dados["descoberta"] = mesclar_descoberta(atual.get("descoberta"))
    dados["geracao"] = mesclar_geracao(atual.get("geracao"))
    dados["publicacao"] = mesclar_publicacao(atual.get("publicacao"), atual.get("youtube"))
    dados["feedback"] = mesclar_feedback(atual.get("feedback"))

    try:
        validado = TipoConfig(**dados)
    except ValidationError as e:
        return templates.TemplateResponse(
            "_tipos_config_tab.html",
            {"request": request, "tipo": tipo_atual, "campos_config": _campos_config(dados),
             "erro": _formatar_erros(e), "sucesso": False},
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
        {"request": request, "tipo": tipo, "campos_config": _campos_config(tipo.config.get_all()),
         "erro": None, "sucesso": True},
    )
