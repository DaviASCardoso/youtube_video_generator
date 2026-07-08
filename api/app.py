from contextlib import asynccontextmanager
from pathlib import Path
import os
import secrets
import socket

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from operacoes import scheduler as scheduler_mod
from api.auth import RequerLoginMiddleware, auth_ativo
from api.routers import aprovacoes, assets, auth, conformidade, configuracoes, descoberta, execucoes, feedback, geracao, operacao, publicacao, temas, tipos
from config import caminhos

BASE = Path(__file__).parent


def _ips_locais() -> list[str]:
    """Lista os IPv4 locais da máquina, um por interface de rede ativa (Wi-Fi,
    Ethernet, etc). A máquina pode estar em mais de uma rede ao mesmo tempo —
    por isso listamos todos, em vez de adivinhar um só (uma interface Ethernet
    e uma Wi-Fi, por exemplo, normalmente ficam em sub-redes diferentes e não
    conseguem se enxergar)."""
    try:
        _, _, ips = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        ips = []

    ips = [ip for ip in ips if not ip.startswith("127.")]
    return ips or ["127.0.0.1"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria a árvore de cada raiz de armazenamento (saída, execuções, tendências,
    # tipos). Um mount (NAS) ausente/somente-leitura não derruba o painel — ele
    # precisa subir para o ajuste poder ser corrigido em /configuracoes —, mas
    # avisa de forma acionável (e o dashboard mostra o sinal).
    problemas = caminhos.garantir_raizes()
    if problemas:
        print("\n" + caminhos.mensagem_problemas(problemas) + "\n")

    scheduler_mod.iniciar()

    porta = os.environ.get("PORT", "8000")
    print("\nPainel disponível em:")
    print(f"  Nesta máquina : http://127.0.0.1:{porta}")
    for ip in _ips_locais():
        print(f"  Na rede local : http://{ip}:{porta}  (requer --host 0.0.0.0)")
    if auth_ativo():
        print("  Login ATIVO (ADMIN_USER/ADMIN_PASSWORD do .env).")
    else:
        print("  AVISO: login DESATIVADO — qualquer um na rede acessa o painel.")
        print("         Defina ADMIN_USER e ADMIN_PASSWORD no .env para exigir login.")
    print()

    yield
    scheduler_mod.parar()


app = FastAPI(title="Gerador de Vídeos", lifespan=lifespan)

# Ordem importa: o RequerLoginMiddleware lê scope["session"], então o
# SessionMiddleware precisa ficar por fora (rodar antes). Como add_middleware
# empilha de dentro para fora, o SessionMiddleware é adicionado por último.
app.add_middleware(RequerLoginMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_hex(32),
    same_site="lax",
    https_only=False,  # painel roda em HTTP na rede local
)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

_pasta_saida = caminhos.raiz("saida")
_pasta_saida.mkdir(parents=True, exist_ok=True)
app.mount("/saida", StaticFiles(directory=_pasta_saida), name="saida")

app.include_router(auth.router)
app.include_router(configuracoes.router)
app.include_router(tipos.router)
app.include_router(assets.router)
app.include_router(descoberta.router)
app.include_router(geracao.router)
app.include_router(publicacao.router)
app.include_router(feedback.router)
app.include_router(feedback.painel)
app.include_router(operacao.router)
app.include_router(conformidade.router)
app.include_router(temas.router)
app.include_router(execucoes.router)
app.include_router(aprovacoes.router)


@app.get("/")
def raiz():
    return RedirectResponse(url="/tipos")
