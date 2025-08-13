from paperpi.daemon.controller import DaemonController
from paperpi.daemon.http_server import start_http_server
from paperpi.library.config_utils import load_yaml_file
# from paperpi.library.config_utils import load_app_config
from paperpi.library.config_utils import validate_config
from paperpi.library.schema_expand import REGISTRY, expand_tokens_in_schema
from paperpi.providers.display_types import get_display_types


import logging
import time
import select

logger = logging.getLogger(__name__)

def daemon_loop(controller: DaemonController) -> None:
    """
    Basic daemon loop with HTTP server. Keeps running until controller.running is False.
    """
    logger.info("Starting daemon loop")
    
    # register token substitution for the YAML files
    REGISTRY.register('DISPLAY_TYPES', get_display_types)

    config_files = controller.config_store.get('configuration_files', {})
    controller.set_config({'app_config': []}, scope='configuration_issues')


    file_app_config = config_files.get('file_app_config', '')
    file_app_schema = config_files.get('file_app_schema', '')
    try:
        app_config = load_yaml_file(file_app_config)
        key = app_config.get('configuration_files', {}).get('key_application_schema', 'main')
        app_config = app_config.get(key, {})
        app_schema = load_yaml_file(file_app_schema)
        app_schema = app_schema.get(key, {})
        # expand tokens as needed based on registered substitutions
        app_schema = expand_tokens_in_schema(app_schema)

        validated_app_config, errors = validate_config(config=app_config, schema=app_schema)


        
    except FileNotFoundError as e:
        logger.error(f'Failed to open file {file_app_config}: {e}')
        controller.stop()
        return
    


    # try:
    #     app_config, errors = load_app_config(config_files)
    # except Exception as e:
    #     logger.error(f"Failed to load configuration: {e}")
    #     controller.stop()
    #     return
    


    controller.set_config(validated_app_config, scope='app')

    if errors:
        controller.config_store['configuration_issues']['app_config'] = errors

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
