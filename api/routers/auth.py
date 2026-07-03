from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from api.auth import checar_credenciais, destino_seguro
from api.templating import templates

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def pagina_login(request: Request, next: str = "/"):
    # já logado? não faz sentido mostrar o formulário de novo
    if request.session.get("usuario"):
        return RedirectResponse(url=destino_seguro(next), status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "erro": None, "next": destino_seguro(next)},
    )


@router.post("/login", response_class=HTMLResponse)
def processar_login(
    request: Request,
    usuario: str = Form(...),
    senha: str = Form(...),
    next: str = Form("/"),
):
    if checar_credenciais(usuario, senha):
        request.session["usuario"] = usuario
        return RedirectResponse(url=destino_seguro(next), status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "erro": "Usuário ou senha inválidos.",
            "next": destino_seguro(next),
        },
        status_code=401,
    )


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
