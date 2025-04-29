from fastapi import Depends
from fastapi.datastructures import FormData
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

async def parse_config_form(request: Request) -> dict:
    form: FormData = await request.form()
    config_dict = {}

    for key, value in form.multi_items():
        val_lower = value.lower()
        if val_lower in ['on', 'true', 'false']:
            config_dict[key] = val_lower == 'true' or val_lower == 'on'
        else:
            try:
                # First try integer
                config_dict[key] = int(value)
            except ValueError:
                try:
                    # Then try float
                    config_dict[key] = float(value)
                except ValueError:
                    config_dict[key] = value

    return config_dict

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

from fastapi import Form
from fastapi.responses import HTMLResponse

@router.post('/config/check_app', response_class=HTMLResponse)
async def post_config_check_app(request: Request, form_data: dict = Depends(parse_config_form), settings: Settings = Depends(get_settings)):
    """
    Accepts YAML-formatted config from a form, submits it to the daemon API for validation,
    and returns config.html with errors and suggestions highlighted.
    """
    submitted_config = form_data

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'{settings.daemon_url}/config/check_app',
                json=submitted_config
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as e:
        result = {'error': f'Failed to connect to daemon: {e}'}

    # Fetch latest schema for context
    try:
        response_files = await client.get(f'{settings.daemon_url}/config/configuration_files')
        response_files.raise_for_status()
        config_files = response_files.json().get('data', {})
        schema_path = Path(config_files.get('file_app_schema', ''))
        schema_key = config_files.get('key_application_schema', 'main')

        if schema_path and schema_path.exists():
            with open(schema_path) as f:
                schema_data = yaml.safe_load(f)
                schema = schema_data.get(schema_key, {})
        else:
            schema = {}
    except Exception:
        schema = {}

    config_items = []
    for key, value in submitted_config.items():
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
        'result': result.get('data', result)
    })