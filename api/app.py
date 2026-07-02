from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api import scheduler as scheduler_mod
from api.routers import configuracoes

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler_mod.iniciar()
    yield
    scheduler_mod.parar()


app = FastAPI(title="Gerador de Vídeos", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

app.include_router(configuracoes.router)


@app.get("/")
def raiz():
    return RedirectResponse(url="/tipos")
