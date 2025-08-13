import logging
from fastapi import Depends
from fastapi.datastructures import FormData

# from fastapi import Form
from fastapi.responses import HTMLResponse
from paperpi.web.settings import get_settings, Settings
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
import yaml
import httpx
import sys
from pathlib import Path
from paperpi.constants import FNAME_APPLICATION_SCHEMA

# sys.path.append(str(Path(__file__).resolve().parents[3]))
# from paperpi.library.config_utils import load_yaml_file

logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory="paperpi/web/templates")

def coerce_by_schema(values: dict, schema: dict) -> dict:
    """Coerce submitted values to types declared in the schema.

    - str: ensure value is a string (e.g., 1 -> "1")
    - int: cast to int
    - float: cast to float (e.g., 3 -> 3.0)
    - bool: accept true/false/on/off/1/0/yes/no
    Unknown or missing types default to string preservation.
    """
    out = {}
    for k, v in values.items():
        rules = schema.get(k, {}) if isinstance(schema, dict) else {}
        t = (rules.get('type') or 'str').lower()

        # Normalize common string inputs
        sval = v
        if isinstance(v, str):
            sval = v.strip()

        try:
            if t in ('int', 'integer'):
                out[k] = int(sval)
            elif t in ('float', 'double', 'number'):
                out[k] = float(sval)
            elif t in ('bool', 'boolean'):
                s = str(sval).lower()
                out[k] = s in ('true', '1', 'on', 'yes')
            elif t in ('str', 'string'):
                # Ensure string even if parse step produced int/float/bool
                out[k] = '' if sval is None else str(sval)
            else:
                # Unknown type: do not coerce
                out[k] = sval
        except Exception:
            # On coercion failure, keep original; validator will flag
            out[k] = sval
    return out

async def parse_config_form(request: Request) -> dict:
    form: FormData = await request.form()
    config_dict = {}

    logger.debug(f'parsing form data:\n{form}')
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
    logger.debug(f'parsed dict:\n{config_dict}')
    return config_dict

@router.get('/config')
async def get_config(request: Request, settings: Settings = Depends(get_settings)):
    try:
        async with httpx.AsyncClient() as client:
            # Fetch app config from daemon
            resp_cfg = await client.get(f'{settings.daemon_url}/config/app')
            resp_cfg.raise_for_status()
            full_response = resp_cfg.json()
            config_data = full_response.get('data', {})

    except httpx.HTTPError as e:
        config_data = {}
        logger.error(f"Failed to fetch config from daemon: {e}")

    try:
        async with httpx.AsyncClient() as client:
            # fetch schema from daemon
            resp_schema = await client.get(f'{settings.daemon_url}/schema/{FNAME_APPLICATION_SCHEMA}')
            resp_schema.raise_for_status()
            application_config = await client.get(f'{settings.daemon_url}/config/configuration_files')
            # use the daemon API to get the name of the main configuration key
            config_key = application_config.json().get('data', {}).get('key_application_schema', 'NONE')
            schema = resp_schema.json().get('data', {}).get('schema', {}).get(config_key, {}) or {}
    except httpx.HTTPError as e:
        schema = {}
        logger.error(f'Failed to fetch schema from daemon: {e}')

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


@router.post('/config/check_app', response_class=HTMLResponse)
async def post_config_check_app(
    request: Request,
    form_data: dict = Depends(parse_config_form),
    settings: Settings = Depends(get_settings)
):
    """
    Submit form data to the daemon validator, using the application schema
    fetched from /schema/<FNAME_APPLICATION_SCHEMA>.
    """
    submitted_config = form_data

    # 1) Fetch the schema from the daemon schema endpoint
    schema = {}
    try:
        async with httpx.AsyncClient() as client:
            resp_schema = await client.get(f'{settings.daemon_url}/schema/{FNAME_APPLICATION_SCHEMA}')
            resp_schema.raise_for_status()
            application_config = await client.get(f'{settings.daemon_url}/config/configuration_files')
            # use the daemon API to get the name of the main configuration key
            config_key = application_config.json().get('data', {}).get('key_application_schema', 'NONE')
            schema = resp_schema.json().get('data', {}).get('schema', {}).get(config_key, {}) or {}
    except httpx.HTTPError as e:
        # If schema cannot be loaded, render error but keep submitted values visible
        return templates.TemplateResponse('config.html', {
            'request': request,
            'config_items': sorted([
                {
                    'key': k,
                    'value': v,
                    'description': '',
                    'default': ''
                } for k, v in submitted_config.items()
            ], key=lambda x: x['key']),
            'schema': {},
            'result': {'error': f'Failed to load schema from daemon: {e}'}
        })
    logger.debug(f'daemon provided schema:\n{schema}')
    logger.debug(f'form data (pre-coerce):\n{submitted_config}')

    # Coerce submitted values according to schema types (int->float, etc.)
    submitted_config = coerce_by_schema(submitted_config, schema)
    logger.debug(f'form data (post-coerce):\n{submitted_config}')

    # 2) Call daemon /check_config with the submitted config and resolved schema
    try:
        async with httpx.AsyncClient() as client:
            payload = {'config': submitted_config, 'schema': schema}
            resp_check = await client.post(f'{settings.daemon_url}/check_config', json=payload)
            # Do not raise for status here; we still want to show problems if 4xx/5xx occurs
            if resp_check.status_code == 200:
                data = resp_check.json()
                result = data.get('data', data)
            else:
                result = {'error': f'Daemon returned {resp_check.status_code}: {resp_check.text}'}
    except httpx.HTTPError as e:
        result = {'error': f'Failed to connect to daemon: {e}'}

    # 3) Build items for the template from the submitted values and schema metadata
    config_items = []
    logger.debug(f'submited_config:\n{submitted_config}')
    for key, value in submitted_config.items():
        rules = schema.get(key, {}) if isinstance(schema, dict) else {}
        entry = {
            'key': key,
            'value': value,
            'description': rules.get('description', 'No description available.'),
            'default': rules.get('default', 'No default available.'),
        }
        config_items.append(entry)
    config_items = sorted(config_items, key=lambda x: x['key'])
    logger.debug(f'config_items:\n{config_items}')

    return templates.TemplateResponse('config.html', {
        'request': request,
        'config_items': config_items,
        'schema': schema,
        'result': result,
    })