from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse

from api.templating import templates
from config.tipos import carregar_tipo, TipoVideo
from scripts.compositor import EMOCAO_PADRAO, EMOCOES, caminho_personagem

router = APIRouter(prefix="/tipos/{id}/assets", tags=["assets"])

ARQUIVOS_TEXTO = (
    "system_prompt_script.txt",
    "system_prompt_prompt.txt",
    "system_prompt_cena.txt",
    "style_prompt.txt",
)


def contexto_prompts(tipo: TipoVideo) -> dict:
    conteudos = {}
    for nome in ARQUIVOS_TEXTO:
        caminho = tipo.assets_dir / nome
        conteudos[nome] = caminho.read_text(encoding="utf-8") if caminho.exists() else ""

    return {
        "tipo": tipo,
        "conteudos": conteudos,
        "tem_imagem": (tipo.assets_dir / "imagem_referencia.png").exists(),
        "emocoes": EMOCOES,
        "emocao_padrao": EMOCAO_PADRAO,
        "personagens": {e: caminho_personagem(tipo.assets_dir, e).exists() for e in EMOCOES},
    }


@router.get("/imagem_referencia", response_class=FileResponse)
def obter_imagem(id: str):
    tipo = carregar_tipo(id)
    caminho = tipo.assets_dir / "imagem_referencia.png"
    if not caminho.exists():
        return HTMLResponse("Sem imagem de referência.", status_code=404)
    return FileResponse(caminho, media_type="image/png")


@router.post("/imagem_referencia", response_class=HTMLResponse)
def enviar_imagem(id: str, request: Request, arquivo_imagem: UploadFile = File(...)):
    tipo = carregar_tipo(id)
    erro = None

    if arquivo_imagem.content_type != "image/png":
        erro = "A imagem de referência precisa ser um arquivo PNG."
    else:
        tipo.assets_dir.mkdir(parents=True, exist_ok=True)
        (tipo.assets_dir / "imagem_referencia.png").write_bytes(arquivo_imagem.file.read())

    tipo = carregar_tipo(id)
    return templates.TemplateResponse(
        "_tipos_prompts_tab.html",
        {"request": request, **contexto_prompts(tipo), "erro": erro, "sucesso": erro is None},
        status_code=422 if erro else 200,
    )


@router.delete("/imagem_referencia", response_class=HTMLResponse)
def remover_imagem(id: str, request: Request):
    tipo = carregar_tipo(id)
    caminho = tipo.assets_dir / "imagem_referencia.png"
    erro = None

    if caminho.exists():
        try:
            caminho.unlink()
        except OSError:
            erro = "Não foi possível remover a imagem agora (arquivo em uso). Tente novamente."

    tipo = carregar_tipo(id)
    return templates.TemplateResponse(
        "_tipos_prompts_tab.html",
        {"request": request, **contexto_prompts(tipo), "erro": erro, "sucesso": erro is None},
        status_code=409 if erro else 200,
    )


@router.get("/personagem/{emocao}", response_class=FileResponse)
def obter_personagem(id: str, emocao: str):
    if emocao not in EMOCOES:
        return HTMLResponse("Emoção inválida.", status_code=404)

    tipo = carregar_tipo(id)
    caminho = caminho_personagem(tipo.assets_dir, emocao)
    if not caminho.exists():
        return HTMLResponse("Sem PNG para essa emoção.", status_code=404)
    return FileResponse(caminho, media_type="image/png")


@router.post("/personagem/{emocao}", response_class=HTMLResponse)
def enviar_personagem(id: str, emocao: str, request: Request, arquivo_imagem: UploadFile = File(...)):
    if emocao not in EMOCOES:
        return HTMLResponse("Emoção inválida.", status_code=404)

    tipo = carregar_tipo(id)
    erro = None

    if arquivo_imagem.content_type != "image/png":
        erro = f"O personagem ({emocao}) precisa ser um arquivo PNG (idealmente com fundo transparente)."
    else:
        caminho = caminho_personagem(tipo.assets_dir, emocao)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(arquivo_imagem.file.read())

    tipo = carregar_tipo(id)
    return templates.TemplateResponse(
        "_tipos_prompts_tab.html",
        {"request": request, **contexto_prompts(tipo), "erro": erro, "sucesso": erro is None},
        status_code=422 if erro else 200,
    )


@router.delete("/personagem/{emocao}", response_class=HTMLResponse)
def remover_personagem(id: str, emocao: str, request: Request):
    if emocao not in EMOCOES:
        return HTMLResponse("Emoção inválida.", status_code=404)

    tipo = carregar_tipo(id)
    caminho = caminho_personagem(tipo.assets_dir, emocao)
    erro = None

    if caminho.exists():
        try:
            caminho.unlink()
        except OSError:
            erro = "Não foi possível remover o PNG agora (arquivo em uso). Tente novamente."

    tipo = carregar_tipo(id)
    return templates.TemplateResponse(
        "_tipos_prompts_tab.html",
        {"request": request, **contexto_prompts(tipo), "erro": erro, "sucesso": erro is None},
        status_code=409 if erro else 200,
    )


@router.post("/{arquivo}", response_class=HTMLResponse)
def salvar_texto(id: str, arquivo: str, request: Request, conteudo: str = Form(...)):
    if arquivo not in ARQUIVOS_TEXTO:
        return HTMLResponse("Arquivo inválido.", status_code=404)

    tipo = carregar_tipo(id)
    conteudo = conteudo.strip()
    erro = None

    if not conteudo:
        erro = f"{arquivo}: o conteúdo não pode ficar vazio."
    else:
        (tipo.assets_dir / arquivo).write_text(conteudo, encoding="utf-8")

    tipo = carregar_tipo(id)
    return templates.TemplateResponse(
        "_tipos_prompts_tab.html",
        {"request": request, **contexto_prompts(tipo), "erro": erro, "sucesso": erro is None},
        status_code=422 if erro else 200,
    )
