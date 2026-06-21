from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import init_db
from routers import auth as auth_router
from routers import logs as logs_router
from routers import projects as projects_router
from routers import webhooks as webhooks_router

app = FastAPI(title="GitPulse")

init_db()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(auth_router.router)
app.include_router(projects_router.router)
app.include_router(logs_router.router)
app.include_router(webhooks_router.router)


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/")
def index_page(request: Request):
    return templates.TemplateResponse(request, "index.html")
