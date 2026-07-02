from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).parent

templates = Jinja2Templates(directory=BASE / "templates")

app = FastAPI(title="Gerador de Vídeos")

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def raiz():
    return RedirectResponse(url="/tipos")
