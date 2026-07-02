from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api import scheduler as scheduler_mod
from api.routers import assets, configuracoes, execucoes, temas, tipos
from config.sistema import sistema

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler_mod.iniciar()
    yield
    scheduler_mod.parar()


app = FastAPI(title="Gerador de Vídeos", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

_pasta_saida = Path(sistema.get("saida.pasta_base"))
_pasta_saida.mkdir(parents=True, exist_ok=True)
app.mount("/saida", StaticFiles(directory=_pasta_saida), name="saida")

app.include_router(configuracoes.router)
app.include_router(tipos.router)
app.include_router(assets.router)
app.include_router(temas.router)
app.include_router(execucoes.router)


@app.get("/")
def raiz():
    return RedirectResponse(url="/tipos")
