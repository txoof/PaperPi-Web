from http.server import HTTPServer
import logging
from paperpi.daemon.http_handler import RootHandler

logger = logging.getLogger(__name__)

def start_http_server(port: int = 2822, controller=None) -> HTTPServer:
    server_address = ('0.0.0.0', port)
    logger.debug(f'Starting API at: {server_address}')
    httpd = HTTPServer(server_address, RootHandler)
    httpd.controller = controller
    logger.info(f"HTTP server running on port {port}")
    return httpd