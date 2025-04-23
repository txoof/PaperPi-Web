from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
import yaml
import httpx
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[3]))
from paperpi.constants import PATH_APP_CONFIG, FNAME_APPLICATION_SCHEMA

router = APIRouter()

templates = Jinja2Templates(directory="paperpi/web/templates")

@router.get('/config')
async def get_config(request: Request):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get('http://localhost:2822/config/app')
            response.raise_for_status()
            config_data = response.json()
    except httpx.HTTPError as e:
        config_data = {}
        print(f"[ERROR] Failed to fetch config from daemon: {e}")

    schema_path = PATH_APP_CONFIG / FNAME_APPLICATION_SCHEMA
    if schema_path.exists():
        with open(schema_path) as f:
            schema_data = yaml.safe_load(f)
            schema = schema_data.get('main', {})
    else:
        schema = {}

    config_items = []
    for key, value in config_data.items():
        description = schema.get(key, {}).get('description', 'No description available.')
        config_items.append({'key': key, 'value': value, 'description': description})

    return templates.TemplateResponse('config.html', {
        'request': request,
        'config_items': config_items
    })


@router.get('/config/edit')
async def edit_config(request: Request):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get('http://localhost:2822/config/app')
            response.raise_for_status()
            config_data = response.json()
    except httpx.HTTPError as e:
        config_data = {}
        print(f"[ERROR] Failed to fetch config from daemon: {e}")

    schema_path = PATH_APP_CONFIG / FNAME_APPLICATION_SCHEMA
    if schema_path.exists():
        with open(schema_path) as f:
            schema_data = yaml.safe_load(f)
            schema = schema_data.get('main', {})
    else:
        schema = {}

    config_items = []
    for key, value in config_data.items():
        meta = schema.get(key, {})
        editable = meta.get('editable', True)
        config_items.append({
            'key': key,
            'value': value,
            'description': meta.get('description', 'No description available.'),
            'editable': editable
        })

    return templates.TemplateResponse('config_edit.html', {
        'request': request,
        'config_items': config_items
    })