import json

def handle_status_route(handler, controller):
    """Respond with the daemon's current running state."""
    response = {
        'running': controller.running
    }
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(response).encode())


# This dictionary maps URL paths to their corresponding route handler functions.
# Each entry associates a specific route (e.g., '/status') with a function that
# processes the request and generates the appropriate response.
# These routes are discovered and registered by the system to enable automatic
# dispatching and documentation (e.g., via the /help route).
ROUTES = {
    '/status': handle_status_route
}