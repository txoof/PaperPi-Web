# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.4
#   kernelspec:
#     display_name: Python (PaperPi-Web-venv-33529be2c6)
#     language: python
#     name: paperpi-web-venv-33529be2c6
# ---

# +
# web/routes/base.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Flag will be imported from paperpi (global state for now)
daemon_running = True
systemd_mode = False  # You'll import the real one later

@router.get('/', response_class=HTMLResponse)
async def home():
    return """
    <h1>Welcome to PaperPi</h1>
    <p>Stub login page or config interface will go here.</p>
    <p>Try POSTing to /stop to halt the daemon.</p>
    """

@router.get('/login')
async def login():
    return "Login page (to be implemented)."

@router.post('/stop')
async def stop():
    global daemon_running
    daemon_running = False
    logger.info("Received /stop request; shutting down daemon and FastAPI...")

    # In systemd mode, just return
    if not systemd_mode:
        logger.info("stopped: press ctrl+c to exit")

    return JSONResponse(content={"message": "Stopping daemon..."})
