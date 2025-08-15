# paperpi/daemon/routes/config_routes.py
import logging

from http import HTTPStatus
from urllib.parse import urlparse

import json
from typing import Any, Dict
from paperpi.library.schema_expand import expand_tokens_in_schema

logger = logging.getLogger(__name__)
from paperpi.library.config_utils import check_config_problems, update_yaml_file


def _send_json(handler, status: int, payload: Dict[str, Any]):
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(payload, indent=2, default=str).encode())


def _parse_json(handler) -> Dict[str, Any] | None:
    try:
        length = int(handler.headers.get('Content-Length', '0'))
    except ValueError:
        length = 0
    body = handler.rfile.read(length).decode('utf-8') if length > 0 else '{}'
    try:
        payload = json.loads(body or '{}')
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    _send_json(handler, HTTPStatus.BAD_REQUEST, {'error': 'Invalid JSON body'})
    return None


def _registry_lookup(controller, name: str) -> Dict[str, Any] | None:
    reg = (controller.config_store or {}).get('registry', {})
    return reg.get(name)


def handle_config_registry(handler, controller):
    """
    GET /config/registry
    Returns the current configuration registry from controller.config_store['registry'].
    """
    registry = (controller.config_store or {}).get('registry', {})
    _send_json(handler, HTTPStatus.OK, {'data': registry})


def handle_config_route(handler, controller):
    """
    GET /config
    GET /config/<name>

    Returns configuration data from the in-memory controller store.
    - `/config` returns the entire `config_store` (useful for debugging).
    - `/config/<name>` returns the config for a registered name (e.g., `app`).
      If `<name>` is not in the registry, falls back to direct sections in the store.

    Responses:
    - 200 JSON on success
    - 404 JSON if `<name>` is unknown
    - 400 JSON for malformed paths
    """
    path = urlparse(handler.path).path
    parts = path.strip('/').split('/')
    store = controller.config_store or {}

    # /config
    if len(parts) == 1:
        response = {
            'data': store,
            'server_info': {
                'current_port': store.get('app', {}).get('daemon_http_port', 'unknown')
            }
        }
        return _send_json(handler, HTTPStatus.OK, response)

    # /config/<name>
    if len(parts) == 2:
        name = parts[1]
        reg = (store.get('registry') or {})
        if name in reg:
            payload = store.get(name, {})
            return _send_json(handler, HTTPStatus.OK, {'data': payload})
        # Back-compat: allow direct sections in store
        if name in store:
            return _send_json(handler, HTTPStatus.OK, {'data': store[name]})
        return _send_json(handler, HTTPStatus.NOT_FOUND, {
            'error': f"Unknown config name '{name}'",
            'available': list(reg.keys())
        })

    # Anything else is bad request
    return _send_json(handler, HTTPStatus.BAD_REQUEST, {
        'error': f"Unsupported /config path: {'/'.join(parts)}"
    })


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


# POST /config/check/<name>
def handle_config_check_name(handler, controller):
    """
    POST /config/check/<name>

    Validate a submitted config object for the given `<name>` using the daemon's
    schema (effective, with tokens expanded). The request body must be JSON with:

      { "config": { ... } }

    Payload should be a FLAT mapping for the selected schema section (e.g., the
    `main` section for `app`). The route does not require the client to supply a
    schema; it is resolved based on the registry.

    Responses:
    - 200 JSON: { data: { submitted: {...}, problems: {...} } }
    - 400 JSON: invalid path or body
    - 404 JSON: unknown `<name>`
    - 500 JSON: internal validation or schema load error
    """
    path = urlparse(handler.path).path
    parts = path.strip('/').split('/')  # expect ['config','check','<name>']
    if len(parts) != 3 or not parts[2]:
        return _send_json(handler, HTTPStatus.BAD_REQUEST, {'error': 'Path must be /config/check/<name>'})
    name = parts[2]

    reg_entry = _registry_lookup(controller, name)
    if not reg_entry:
        return _send_json(handler, HTTPStatus.NOT_FOUND, {'error': f"Unknown config name '{name}'"})

    payload = _parse_json(handler)
    if payload is None:
        return  # _parse_json already responded
    cfg = payload.get('config')
    if not isinstance(cfg, dict):
        return _send_json(handler, HTTPStatus.BAD_REQUEST, {'error': 'Body must include a config object'})

    # Resolve schema: prefer pre-expanded in controller, else load+expand now
    schemas = (controller.config_store or {}).get('schemas', {})
    schema_key = reg_entry.get('schema_key') or 'main'
    if name == 'app' and 'application_effective' in schemas:
        schema = schemas['application_effective']
    else:
        # Fallback: try to load and expand ad-hoc (keeps generic behavior)
        try:
            from paperpi.library.config_utils import load_yaml_file
            schema_file = reg_entry.get('schema_file')
            full = load_yaml_file(schema_file) if schema_file else {}
            selected = full.get(schema_key, full) if isinstance(full, dict) else {}
            schema = expand_tokens_in_schema(selected)
        except Exception as e:
            logger.error("check/%s: failed to load schema: %s", name, e, exc_info=True)
            return _send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {'error': f'Failed to load schema for {name}: {e}'})

    try:
        problems = check_config_problems(cfg, schema, strict=True)
        logger.info("[check] name=%s problems=%d", name, len(problems or {}))
    except Exception as e:
        logger.error("[check] name=%s validation error: %s", name, e, exc_info=True)
        return _send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {'error': f'Validation error: {e}'})

    return _send_json(handler, HTTPStatus.OK, {
        'data': {
            'submitted': cfg,
            'problems': problems or {},
        }
    })


# POST /config/write/<name>
def handle_config_write_name(handler, controller):
    """
    POST /config/write/<name>

    Write a submitted config object for the given `<name>` to disk. The request body
    must be JSON with:

      { "config": { ... } }

    The daemon wraps the flat mapping under the configured `schema_key` (e.g.,
    `main`) and deep-merges into the on-disk YAML using `update_yaml_file`. The
    in-memory controller config for `<name>` is updated on success.

    Responses:
    - 200 JSON: { data: { written: bool, diff: {...}, message: str } }
    - 400 JSON: invalid path or body
    - 404 JSON: unknown `<name>`
    - 500 JSON: write failure
    """
    path = urlparse(handler.path).path
    parts = path.strip('/').split('/')  # expect ['config','write','<name>']
    if len(parts) != 3 or not parts[2]:
        return _send_json(handler, HTTPStatus.BAD_REQUEST, {'error': 'Path must be /config/write/<name>'})
    name = parts[2]

    reg_entry = _registry_lookup(controller, name)
    if not reg_entry:
        return _send_json(handler, HTTPStatus.NOT_FOUND, {'error': f"Unknown config name '{name}'"})

    payload = _parse_json(handler)
    if payload is None:
        return
    cfg = payload.get('config')
    if not isinstance(cfg, dict):
        return _send_json(handler, HTTPStatus.BAD_REQUEST, {'error': 'Body must include a config object'})

    config_file = reg_entry.get('config_file')
    if not config_file:
        return _send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {'error': f"No config_file set for '{name}' in registry"})

    try:
        # Wrap payload under the schema key if the on-disk file is namespaced (e.g., `main:`)
        schema_key = reg_entry.get('schema_key') or 'main'
        cfg_to_write = {schema_key: cfg} if schema_key else cfg

        written, diff = update_yaml_file(config_file, cfg_to_write, backup=True, keep=3)

        # Update in-memory view (keep it flat for the currently loaded scope)
        current = (controller.config_store or {}).get(name, {})
        if not isinstance(current, dict):
            current = {}
        current.update(cfg)
        controller.set_config(current, scope=name)

        msg = 'Configuration written successfully.' if written else 'No changes to write.'
        return _send_json(handler, HTTPStatus.OK, {'data': {'written': bool(written), 'diff': diff, 'message': msg}})
    except Exception as e:
        logger.error("[write] name=%s error: %s", name, e, exc_info=True)
        return _send_json(handler, HTTPStatus.INTERNAL_SERVER_ERROR, {'error': f'Failed to write configuration: {e}'})


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

# This dictionary maps URL paths to their corresponding route handler functions.
# Each entry associates a specific route (e.g., '/status') with a function that
# processes the request and generates the appropriate response.
# These routes are discovered and registered by the system to enable automatic
# dispatching and documentation (e.g., via the /help route).
ROUTES = {
    # Generic endpoints
    '/config/registry': handle_config_registry,
    '/config/check': handle_config_check_name,   # prefix route for /config/check/<name>
    '/config/write': handle_config_write_name,   # prefix route for /config/write/<name>

    # Read config (index or by name)
    '/config': handle_config_route,

    # Back-compat endpoints
    # '/check_config': handle_check_config,
    # '/config/write_config': handle_write_config,
}