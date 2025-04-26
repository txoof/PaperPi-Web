from fastapi import Depends
from paperpi.web.settings import get_settings, Settings
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
import yaml
import httpx
import sys
from pathlib import Path

# sys.path.append(str(Path(__file__).resolve().parents[3]))
# from paperpi.library.config_utils import load_yaml_file

router = APIRouter()

templates = Jinja2Templates(directory="paperpi/web/templates")

@router.get('/config')
async def get_config(request: Request, settings: Settings = Depends(get_settings)):
    try:
        async with httpx.AsyncClient() as client:
            # Fetch app config
            response = await client.get(f'{settings.daemon_url}/config/app')
            response.raise_for_status()
            full_response = response.json()
            config_data = full_response.get('data', {})

            # Fetch configuration file paths
            response_files = await client.get(f'{settings.daemon_url}/config/configuration_files')
            response_files.raise_for_status()
            config_files = response_files.json().get('data', {})

            schema_path = Path(config_files.get('file_app_schema', ''))
            schema_key = config_files.get('key_application_schema', 'main')
    except httpx.HTTPError as e:
        config_data = {}
        schema_path = None
        schema_key = 'main'
        print(f"[ERROR] Failed to fetch config or config files from daemon: {e}")

    if schema_path and schema_path.exists():
        with open(schema_path) as f:
            schema_data = yaml.safe_load(f)
            schema = schema_data.get(schema_key, {})
    else:
        schema = {}

    config_items = []
    for key, value in config_data.items():
        entry = {
            'key': key,
            'value': value,
            'description': schema.get(key, {}).get('description', 'No description available.'),
            'default': schema.get(key, {}).get('default', 'No default available.')
        }
        config_items.append(entry)

        config_items = sorted(config_items, key=lambda x: x['key'])


    return templates.TemplateResponse('config.html', {
        'request': request,
        'config_items': config_items,
        'schema': schema,
    })