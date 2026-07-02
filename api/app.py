from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api import scheduler as scheduler_mod

BASE = Path(__file__).parent

templates = Jinja2Templates(directory=BASE / "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler_mod.iniciar()
    yield
    scheduler_mod.parar()


app = FastAPI(title="Gerador de Vídeos", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def raiz():
    return RedirectResponse(url="/tipos")
