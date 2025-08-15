# paperpi/daemon/routes/schema_routes.py
from http import HTTPStatus
import json
from pathlib import Path
from urllib.parse import urlparse
import logging

from paperpi.constants import PATH_APP_CONFIG
from paperpi.library.config_utils import load_yaml_file
from paperpi.library.schema_expand import REGISTRY, expand_tokens_in_schema
from paperpi.providers.display_types import get_display_types

logger = logging.getLogger(__name__)

def handle_schema_index(handler, controller):
    """
    GET /schema or /schema/
      -> return a list of available schema files (those containing "_schema.yaml")

    GET /schema/<name-or-filename>
      -> return the contents of that schema file as JSON, excluding the
         top-level key 'schema_information'. The <name-or-filename> may be
         either a base name like 'paperpi_config' or a filename like
         'paperpi_config_schema.yaml'.
    """
    base: Path = PATH_APP_CONFIG

    REGISTRY.register('DISPLAY_TYPES', get_display_types)

    try:
        # Normalize the path and detect if a specific schema is requested
        raw_path = handler.path
        # Remove query string if present
        path = urlparse(raw_path).path
        # Expect prefixes '/schema' or '/schema/'
        tail = path[len('/schema'):].lstrip('/') if path.startswith('/schema') else ''

        # Name-based access: /schema/app (or /schema/application)
        if tail in ('app', 'application'):
            try:
                schemas = (controller.config_store or {}).get('schemas', {})
                effective = schemas.get('application_effective')
                if not isinstance(effective, dict):
                    handler.send_response(HTTPStatus.NOT_FOUND)
                    handler.send_header('Content-Type', 'application/json')
                    handler.end_headers()
                    handler.wfile.write(json.dumps({'error': 'Effective application schema not available'}).encode())
                    return

                payload = {
                    'data': {
                        'name': 'app',
                        'schema': effective,
                    }
                }
                handler.send_response(HTTPStatus.OK)
                handler.send_header('Content-Type', 'application/json')
                handler.end_headers()
                handler.wfile.write(json.dumps(payload, indent=2).encode())
                return
            except Exception as e:
                logger.error('schema/app: unexpected error: %s', e, exc_info=True)
                handler.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                handler.send_header('Content-Type', 'application/json')
                handler.end_headers()
                handler.wfile.write(json.dumps({'error': f'Failed to serve application schema: {e}'}).encode())
                return

        if not tail:
            # Index: list all schemas
            files = []
            if base.exists() and base.is_dir():
                for p in sorted(base.iterdir()):
                    if p.is_file() and p.name.endswith('_schema.yaml'):
                        try:
                            data = load_yaml_file(str(p))
                        except Exception:
                            data = {}
                        info = data.get('schema_information', {}) if isinstance(data, dict) else {}
                        name = p.name[:-len('_schema.yaml')]
                        files.append({
                            'name': name,
                            'file': p.name,
                            'description': info.get('description', ''),
                            'version': info.get('version', None),
                        })
            payload = {
                'data': {
                    'path': str(base.resolve()),
                    'schema': files,
                }
            }
            handler.send_response(HTTPStatus.OK)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(payload, indent=2).encode())
            return

        # Specific schema requested
        candidate = tail

        # Reject unsafe or directory-like candidates
        if not candidate or candidate.endswith('/') or '/' in candidate or '..' in candidate:
            handler.send_response(HTTPStatus.NOT_FOUND)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': f'Schema not found: {candidate}'}).encode())
            return

        # Resolve filename: accept either raw filename or base name (try .yaml then .yml)
        candidates = []
        if candidate.endswith('.yaml') or candidate.endswith('.yml'):
            candidates.append(candidate)
        else:
            candidates.append(f'{candidate}_schema.yaml')
            candidates.append(f'{candidate}_schema.yml')

        target = None
        for fname in candidates:
            p = base / fname
            if p.exists() and p.is_file():
                target = p
                break

        if target is None:
            handler.send_response(HTTPStatus.NOT_FOUND)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': f'Schema not found: {candidate}'}).encode())
            return

        try:
            data = load_yaml_file(str(target))
            data = expand_tokens_in_schema(data)
        except Exception as e:
            handler.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': f'Failed to load schema: {e}'}).encode())
            return

        # Drop the top-level 'schema_information' key if present
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != 'schema_information'}

        payload = {
            'data': {
                'name': candidate.replace('_schema.yaml', ''),
                'file': target.name,
                'schema': data,
            }
        }
        handler.send_response(HTTPStatus.OK)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(payload, indent=2).encode())

    except Exception as e:
        handler.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': f'Unexpected error: {e}'}).encode())


# Register routes for both /schema and /schema/
ROUTES = {
    "/schema": handle_schema_index,
    "/schema/": handle_schema_index,
}