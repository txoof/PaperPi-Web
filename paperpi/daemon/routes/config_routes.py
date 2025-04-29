# paperpi/daemon/routes/config_routes.py
from http import HTTPStatus
from urllib.parse import urlparse

import json


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

# This dictionary maps URL paths to their corresponding route handler functions.
# Each entry associates a specific route (e.g., '/status') with a function that
# processes the request and generates the appropriate response.
# These routes are discovered and registered by the system to enable automatic
# dispatching and documentation (e.g., via the /help route).
ROUTES = {
    '/config': handle_config_route
}