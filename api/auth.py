"""Login do painel (usuário + senha vindos do .env).

O painel não tem autenticação por padrão. Se ADMIN_USER e ADMIN_PASSWORD
estiverem no .env, o acesso passa a exigir login — o que fecha a brecha de
"qualquer um na mesma rede local mexe no painel". A sessão é um cookie assinado
(Starlette SessionMiddleware); sem HTTPS, isso mantém curiosos/dispositivos da
rede de fora, mas não protege contra quem consegue farejar o tráfego da rede.

As credenciais são lidas do ambiente a cada chamada (não em variáveis de módulo)
para que os testes possam injetá-las e para pegar mudanças sem reimportar.
"""

import os
from secrets import compare_digest
from urllib.parse import quote

from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

# Caminhos que continuam abertos mesmo com login ativo: a própria tela de login e
# os estáticos (CSS/JS de que a tela de login precisa para renderizar).
_PREFIXOS_ISENTOS = ("/login", "/logout", "/static")


def auth_ativo() -> bool:
    """True se o login está configurado (ambas as credenciais presentes no .env)."""
    return bool(os.getenv("ADMIN_USER")) and bool(os.getenv("ADMIN_PASSWORD"))


def checar_credenciais(usuario: str, senha: str) -> bool:
    """Confere usuário+senha contra o .env, em tempo constante.

    Retorna False se o login não estiver configurado — não dá para autenticar
    contra credenciais inexistentes.
    """
    admin_user = os.getenv("ADMIN_USER")
    admin_senha = os.getenv("ADMIN_PASSWORD")
    if not admin_user or not admin_senha:
        return False
    usuario_ok = compare_digest(usuario, admin_user)
    senha_ok = compare_digest(senha, admin_senha)
    return usuario_ok and senha_ok


def destino_seguro(destino: str | None) -> str:
    """Sanitiza o parâmetro `next` para evitar open redirect.

    Só aceita caminhos internos (começando com uma única "/"); qualquer outra
    coisa (URL absoluta, "//host", vazio) cai na raiz.
    """
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return "/"


def _caminho_isento(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p) for p in _PREFIXOS_ISENTOS)


class RequerLoginMiddleware:
    """Middleware ASGI puro que exige sessão autenticada.

    É ASGI puro de propósito (não BaseHTTPMiddleware): o endpoint de log ao vivo
    usa StreamingResponse (SSE), e o BaseHTTPMiddleware quebra respostas em
    streaming. Roda por dentro do SessionMiddleware, então lê `scope["session"]`.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not auth_ativo():
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        sessao = scope.get("session", {})
        if _caminho_isento(path) or sessao.get("usuario"):
            await self.app(scope, receive, send)
            return

        # Não autenticado: HTMX precisa do header HX-Redirect para trocar a página
        # inteira; um request normal recebe um redirect 303 comum.
        headers = dict(scope.get("headers", []))
        if headers.get(b"hx-request") == b"true":
            resposta = Response(status_code=204, headers={"HX-Redirect": "/login"})
        else:
            resposta = RedirectResponse(url=f"/login?next={quote(path)}", status_code=303)
        await resposta(scope, receive, send)
