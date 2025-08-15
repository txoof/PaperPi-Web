from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings
import os
from pathlib import Path

# ---- Settings ---------------------------------------------------------------

class Settings(BaseSettings):
    daemon_url: str = os.getenv("DAEMON_URL", "http://localhost:2822")

def get_settings() -> Settings:
    return Settings()

# ---- App & Templates --------------------------------------------------------

app = FastAPI(title="PaperPi Web")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---- Routes (minimal for Phase 1) ------------------------------------------

@app.get("/health")
async def health(settings: Settings = get_settings()):
    # Simple health info, plus what daemon URL we’re configured to use
    return JSONResponse({"status": "ok", "daemon_url": settings.daemon_url})

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Temporary landing page; in Phase 2 we’ll redirect to /config/app
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "title": "PaperPi Web", "content": "UI scaffold is running. Phase 2 coming next."},
    )

# Placeholder so you can see the “config page” shell renders
@app.get("/config/app", response_class=HTMLResponse)
async def config_app_shell(request: Request):
    return templates.TemplateResponse(
        "config.html",
        {"request": request, "title": "App Configuration (Phase 1 shell)"},
    )