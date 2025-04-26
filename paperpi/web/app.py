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
from fastapi import FastAPI
# from paperpi.web.settings import Settings
from paperpi.web.routes import config
import httpx

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    daemon_url: str = 'http://localhost:2822'

def get_settings() -> Settings:
    return Settings()

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
    Create and configure a FastAPI application instance for the PaperPi web interface.

    This function sets the daemon API URL used internally by routes to fetch configuration
    and other data from the PaperPi daemon. It then initializes the FastAPI app, attaches
    the application's routes, and returns the app instance.

    Returns:
        FastAPI: A configured FastAPI application instance ready to run.
    """
    settings = Settings()
    
    app = FastAPI()
    app.include_router(config.router)
    return app
