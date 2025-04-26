# dev_main.py
from .app import create_app

"""
Development launcher for the PaperPi web application.

This script creates and configures a FastAPI application instance using
a specific daemon URL, then exposes it as the `app` variable for use with
Uvicorn or other ASGI servers.

To run the server with hot-reloading for development:
    uvicorn paperpi.web.dev_main:app --reload --host 0.0.0.0 --port 8123

The daemon URL is injected here to allow dynamic configuration and
communication with the PaperPi daemon API.
"""

app = create_app()
