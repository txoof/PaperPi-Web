import json

def handle_help_route(handler):
    """Return a list of all available HTTP routes with their docstrings."""
    from paperpi.daemon.routes import ROUTE_REGISTRY  # Delayed import to avoid circularity

    help_data = {
        route: func.__doc__ or "No description"
        for route, func in ROUTE_REGISTRY.items()
    }
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(help_data, indent=2).encode())

# This dictionary maps URL paths to their corresponding route handler functions.
# Each entry associates a specific route (e.g., '/help') with a function that
# processes the request and generates the appropriate response.
# These routes are discovered and registered by the system to enable automatic
# dispatching and documentation (e.g., via the /help route).
ROUTES = {
    '/help': handle_help_route
}