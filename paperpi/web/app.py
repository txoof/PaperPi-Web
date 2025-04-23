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
from paperpi.web.routes import config
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

app = FastAPI()
app.include_router(config.router)
