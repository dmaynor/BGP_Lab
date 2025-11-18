"""Observer backend entrypoint."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .routes import router as api_router

app = FastAPI(title="BGP Observer", version="0.1.0")
app.include_router(api_router, prefix="/api")
templates = Jinja2Templates(directory="/app/frontend/templates")
app.mount("/static", StaticFiles(directory="/app/frontend/static"), name="static")
app.mount("/captures", StaticFiles(directory="/captures"), name="captures")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
