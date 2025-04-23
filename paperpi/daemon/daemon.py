# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.4
#   kernelspec:
#     display_name: Python (PaperPi-Web-venv-33529be2c6)
#     language: python
#     name: paperpi-web-venv-33529be2c6
# ---


import logging
import sys
import json
import time
import threading
import signal
from http.server import BaseHTTPRequestHandler


class DaemonRequestHandler(BaseHTTPRequestHandler):
    """
    Handles HTTP GET requests for the PaperPi daemon.

    This class is used by the daemon's internal HTTP server to provide
    configuration and status information for debugging or integration.
    """

    def do_GET(self):
        """
        Handle GET requests using a dynamic route dispatcher.
        """
        self.routes = {
            '/config/app': (self.handle_config_app, 'Returns the app configuration as JSON'),
            '/shutdown': (self.handle_shutdown, 'Triggers a graceful shutdown of the daemon'),
            '/': (self.handle_help, 'Shows this help message'),
        }

        handler_entry = self.routes.get(self.path)
        if handler_entry:
            handler_func, _ = handler_entry
            handler_func()
        else:
            self.send_json({'error': 'Not found'}, status=404)

    def handle_help(self):
        """
        Returns a JSON list of available HTTP endpoints and their descriptions.
        """
        help_data = [
            {"path": path, "description": description}
            for path, (_, description) in self.routes.items()
        ]
        self.send_json(help_data)

    def handle_config_app(self):
        self.send_json(config_store.get('app', {}))

    def handle_shutdown(self):
        self.send_json({'status': 'shutting down'})
        threading.Thread(target=handle_signal, args=(signal.SIGTERM, None)).start()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))

logger = logging.getLogger(__name__)

config_store = {
}

daemon_running = True

from http.server import HTTPServer

def start_http_server(port=8888):
    """
    Starts an HTTP server in a background thread to serve daemon data.
    """
    server = HTTPServer(('localhost', port), DaemonRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Daemon HTTP server running at http://localhost:{port}")

def set_config(config: dict, scope: str = 'app'):
    config_store[scope] = config

def daemon_loop():
    """
    The background thread that handles e-paper updates.
    It runs until daemon_running = False.
    """
    logger.info("Daemon loop started.")
    while daemon_running:
        logger.info("display update goes here")
        logger.info('morestuff')
        # In production, you might call a function to update the display here
        time.sleep(5)
    logger.info("Daemon loop stopped.")


# from IPython.display import display, clear_output

# current_image_hash = ''
# plugin_manager.update_cycle()
# try:
#     while True:
#         if current_image_hash != plugin_manager.foreground_plugin.image_hash:
#             current_image_hash = plugin_manager.foreground_plugin.image_hash
#             clear_output(wait=True)        
#             display(plugin_manager.foreground_plugin.image)

#         time.sleep(5)
#         plugin_manager.update_cycle()
# except KeyboardInterrupt:
#     logger.info("Stopped update loop")    
# -

def handle_signal(signum, frame):
    """
    Handle SIGINT (Ctrl+C) or SIGTERM (systemctl stop) for a graceful shutdown:
      - Stop the daemon loop
      - Shut down Flask if possible
    """
    logger.info(f"Signal {signum} received, initiating shutdown.")
    global daemon_running
    daemon_running = False

    
    # shtudown web server here
    try:
        pass # shutdown 
    except Exception as e:
        logger.debug(f"Exception while shutting down Flask: {e}")

    # If running in the foreground, user can also press Ctrl+C again, but let's exit gracefully
    sys.exit(0)


