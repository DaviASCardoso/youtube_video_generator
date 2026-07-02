from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse

from api.templating import templates
from config.tipos import carregar_tipo, TipoVideo

router = APIRouter(prefix="/tipos/{id}/assets", tags=["assets"])

ARQUIVOS_TEXTO = ("system_prompt_script.txt", "system_prompt_prompt.txt", "style_prompt.txt")


def contexto_prompts(tipo: TipoVideo) -> dict:
    conteudos = {}
    for nome in ARQUIVOS_TEXTO:
        caminho = tipo.assets_dir / nome
        conteudos[nome] = caminho.read_text(encoding="utf-8") if caminho.exists() else ""

    return {
        "tipo": tipo,
        "conteudos": conteudos,
        "tem_imagem": (tipo.assets_dir / "imagem_referencia.png").exists(),
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
