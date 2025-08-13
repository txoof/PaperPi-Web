from fastapi import FastAPI
from paperpi.web.routes import config
from paperpi.web.settings import get_settings, Settings  # moved from app.py to settings.py
import httpx

async def fetch_app_config():
    """
    Fetch the current application configuration from the PaperPi daemon.

    This function sends an asynchronous HTTP GET request to the daemon's
    internal API at http://localhost:2822/config/app and returns the parsed
    JSON response as a dictionary.

    Returns:
        dict: The application configuration provided by the daemon.

    Raises:
        httpx.HTTPStatusError: If the request returns a non-2xx response.
        httpx.RequestError: For network-related errors.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get('http://localhost:2822/config/app')
        response.raise_for_status()
        return response.json()

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI app instance.

    Returns:
        FastAPI: The configured FastAPI application.
    """
    app = FastAPI()
    app.include_router(config.router)
    return app

# Expose a module-level app for `uvicorn paperpi.web.app:app`
app = create_app()
