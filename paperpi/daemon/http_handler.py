import logging
from http.server import BaseHTTPRequestHandler
import inspect

from paperpi.daemon.routes import ROUTE_REGISTRY

"""
HTTP handler for the PaperPi daemon API.

Defines the RootHandler class, which dispatches HTTP GET requests
to appropriate route handlers based on the request path.
"""

logger = logging.getLogger(__name__)


class RootHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for the PaperPi daemon API.

    Routes incoming GET requests to specific handlers based on the path.
    The handler has access to the main DaemonController instance via
    `self.server.controller`, which is attached during server setup.
    """

    def do_GET(self):
        """
        Handle GET requests by routing to the appropriate handler based on the request path.

        Routes are registered in the ROUTE_REGISTRY. Each function can accept:
        - just the handler (for simple routes), or
        - handler and controller (for controller-aware routes).
        """
        logger.debug("Routing GET request to %s", self.path)
        route_func = ROUTE_REGISTRY.get(self.path)
        
        # Attempt to match route prefixes (e.g., /config/app handled by /config)
        if not route_func:
            logger.debug('searching for prefixed route...')
            for route_prefix, func in ROUTE_REGISTRY.items():
                if self.path.startswith(route_prefix + '/'):
                    route_func = func
                    break
        
        if route_func:
            try:
                sig = inspect.signature(route_func)
                if len(sig.parameters) == 2:
                    route_func(self, self.server.controller)
                else:
                    route_func(self)
            except Exception as e:
                logger.exception("Exception during route dispatch: %s", e)
                self.send_error(500, f"Internal Server Error: {e}")
        else:
            self.send_error(404, f"No route for {self.path}")

    def do_POST(self):
        """
        Handle POST requests by routing to the appropriate handler based on the request path.

        Routes are registered in the ROUTE_REGISTRY. Each function can accept:
        - just the handler (for simple routes), or
        - handler and controller (for controller-aware routes).
        """
        logger.debug("Routing POST request to %s", self.path)
        route_func = ROUTE_REGISTRY.get(self.path)

        # Attempt to match route prefixes (e.g., /config/check_app handled by /config)
        if not route_func:
            logger.debug('searching for prefixed route...')
            for route_prefix, func in ROUTE_REGISTRY.items():
                if self.path.startswith(route_prefix + '/'):
                    route_func = func
                    break

        if route_func:
            try:
                sig = inspect.signature(route_func)
                if len(sig.parameters) == 2:
                    route_func(self, self.server.controller)
                else:
                    route_func(self)
            except Exception as e:
                logger.exception("Exception during route dispatch: %s", e)
                self.send_error(500, f"Internal Server Error: {e}")
        else:
            self.send_error(501, f"Unsupported method ('POST') for {self.path}")

    def log_message(self, format, *args):
        """
        Override BaseHTTPRequestHandler logging to avoid AttributeError when
        parse_request fails before setting self.command/self.path.
        """
        command = getattr(self, 'command', '-')
        # requestline = getattr(self, 'requestline', '') or ''
        # path = getattr(self, 'path', requestline or '-')
        logger.debug(f"HTTP {command}")