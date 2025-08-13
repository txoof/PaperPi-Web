# paperpi/daemon/routes/config_routes.py
import logging

from http import HTTPStatus
from urllib.parse import urlparse

import json

logger = logging.getLogger(__name__)
from paperpi.library.config_utils import check_config_problems, update_yaml_file


def handle_config_route(handler, controller):
    """
    Return specific sections of the controller's current configuration store as JSON.

    The path format is /config or /config/{section}. If a section is provided, only that
    portion of the config_store is returned.
    """

    path = urlparse(handler.path).path
    parts = path.strip('/').split('/')
    config_data = controller.config_store or {}

    # Determine which part of the config to return
    if len(parts) == 1:
        payload = config_data
    elif len(parts) == 2 and parts[1] in config_data:
        payload = config_data[parts[1]]
    else:
        handler.send_response(HTTPStatus.BAD_REQUEST)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'error': f"Config section '{'/'.join(parts[1:])}' not found. Please specify one of the available sections.",
            'available_sections': list(config_data.keys())
        }).encode())
        return

    response = {
        'data': payload,
        'server_info': {
            'current_port': config_data.get('app', {}).get('daemon_http_port', 'unknown')
        }
    }

    handler.send_response(HTTPStatus.OK)
    handler.send_header('Content-Type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(response, indent=2, default=str).encode())



# POST /check_config handler
def handle_check_config(handler, controller):
    """
    POST /check_config
    Accepts JSON: {"config": {...}, "schema": {...}}
    Validates using check_config_problems and returns problems.
    """
    try:
        length = int(handler.headers.get('Content-Length', '0'))
    except ValueError:
        length = 0
    body = handler.rfile.read(length).decode('utf-8') if length > 0 else '{}'

    try:
        payload = json.loads(body or '{}')
    except json.JSONDecodeError:
        handler.send_response(HTTPStatus.BAD_REQUEST)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid JSON body'}).encode())
        return

    if not isinstance(payload, dict):
        handler.send_response(HTTPStatus.BAD_REQUEST)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Body must be a JSON object'}).encode())
        return

    cfg = payload.get('config')
    schema = payload.get('schema')

    if not isinstance(cfg, dict) or not isinstance(schema, dict):
        handler.send_response(HTTPStatus.BAD_REQUEST)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Both "config" and "schema" must be present'}).encode())
        return

    try:
        problems = check_config_problems(cfg, schema, strict=True)
        logger.info(f"check_config: Found {len(problems)} problems: {list(problems.keys()) if problems else 'none'}")
    except Exception as e:
        logger.error(f"check_config: Exception during validation: {e}", exc_info=True)
        handler.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': f'Validation error: {e}'}).encode())
        return

    response = {
        'data': {
            'submitted': cfg,
            'problems': problems,
        }
    }

    handler.send_response(HTTPStatus.OK)
    handler.send_header('Content-Type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(response, indent=2).encode())


# This dictionary maps URL paths to their corresponding route handler functions.
# Each entry associates a specific route (e.g., '/status') with a function that
# processes the request and generates the appropriate response.
# These routes are discovered and registered by the system to enable automatic
# dispatching and documentation (e.g., via the /help route).
def handle_write_config(handler, controller):
    """
    POST /config/write_config
    Accepts JSON: {"config": {...}, "file": "/path/to/file.yaml"}
    Updates the YAML file with the provided config and returns a diff.
    """
    try:
        length = int(handler.headers.get('Content-Length', '0'))
    except ValueError:
        length = 0
    body = handler.rfile.read(length).decode('utf-8') if length > 0 else '{}'

    try:
        payload = json.loads(body or '{}')
    except json.JSONDecodeError:
        handler.send_response(HTTPStatus.BAD_REQUEST)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid JSON body'}).encode())
        return

    if not isinstance(payload, dict):
        handler.send_response(HTTPStatus.BAD_REQUEST)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Body must be a JSON object'}).encode())
        return

    config = payload.get('config')
    file_path = payload.get('file')
    if not isinstance(config, dict) or not isinstance(file_path, str):
        handler.send_response(HTTPStatus.BAD_REQUEST)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Both "config" (dict) and "file" (str) must be present'}).encode())
        return

    try:
        diff = update_yaml_file(file_path, config)
    except Exception as e:
        logger.error(f"write_config: Exception updating YAML: {e}", exc_info=True)
        handler.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': f'Failed to update config file: {e}'}).encode())
        return

    response = {
        'success': True,
        'diff': diff
    }

    handler.send_response(HTTPStatus.OK)
    handler.send_header('Content-Type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(response, indent=2).encode())


ROUTES = {
    '/config': handle_config_route,
    '/check_config': handle_check_config,
    '/config/write_config': handle_write_config,
}