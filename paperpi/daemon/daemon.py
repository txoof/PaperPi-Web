from paperpi.daemon.controller import DaemonController
from paperpi.daemon.http_server import start_http_server
# from paperpi.library.config_utils import load_yaml_file
from paperpi.daemon.config_loader import load_app_config

import logging
import time
import select

logger = logging.getLogger(__name__)



def daemon_loop(controller: DaemonController) -> None:
    """
    Basic daemon loop with HTTP server. Keeps running until controller.running is False.
    """
    logger.info("Starting daemon loop")

    config_files = controller.config_store.get('configuration_files', {})

    try:
        app_config = load_app_config(config_files)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        controller.stop()
        return
    controller.set_config(app_config, scope='app')

    logger.debug(f'Controller.config_store: {controller.config_store}')
    controller.running = True

    daemon_http_port = controller.config_store.get('app', {}).get('daemon_http_port')
    httpd = start_http_server(port=daemon_http_port, controller=controller)
    httpd.socket.settimeout(1.0)  # Avoid blocking forever on request

    last_plugin_update = time.monotonic()

    while controller.running:
        now = time.monotonic()
        if now - last_plugin_update >= 5:
            logger.info("display update goes here")
            last_plugin_update = now

        rlist, _, _ = select.select([httpd.socket], [], [], 1.0)
        if rlist:
            httpd.handle_request()

    logger.info("Daemon loop stopped")
