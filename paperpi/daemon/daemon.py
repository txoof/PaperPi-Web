from paperpi.daemon.controller import DaemonController
from paperpi.daemon.http_server import start_http_server
from paperpi.library.config_utils import load_yaml_file
# from paperpi.library.config_utils import load_app_config
from paperpi.library.config_utils import validate_config
from paperpi.library.schema_expand import REGISTRY, expand_tokens_in_schema
from paperpi.providers.display_types import get_display_types
from paperpi.constants import DAEMON_HTTP_PORT


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

    # Build a small in-memory registry so routes can resolve names generically
    registry = controller.config_store.setdefault('registry', {})
    registry['app'] = {
        'config_file': config_files.get('file_app_config', ''),
        'schema_file': config_files.get('file_app_schema', ''),
        'schema_key' : config_files.get('key_application_schema', 'main')
    }

    registry['plugin_base'] = {
        'schema_file': config_files.get('file_plugin_schema', ''),
    }

    file_app_config = registry['app']['config_file']
    file_app_schema = registry['app']['schema_file']
    key = registry['app']['schema_key']

    try:
        # Load application config and select the namespaced section
        app_config_full = load_yaml_file(file_app_config)
        app_config = app_config_full.get(key, app_config_full) if isinstance(app_config_full, dict) else {}

        # Load application schema (raw), select section, then expand tokens once
        app_schema_full = load_yaml_file(file_app_schema)
        app_schema_raw = app_schema_full.get(key, app_schema_full) if isinstance(app_schema_full, dict) else {}
        app_schema_effective = expand_tokens_in_schema(app_schema_raw)

        # Persist schemas for other routes to reuse
        schemas_bucket = controller.config_store.setdefault('schemas', {})
        schemas_bucket['application_raw'] = app_schema_raw
        schemas_bucket['application_effective'] = app_schema_effective

        # Initialize schema aliases (centralized in controller)
        controller.init_schema_aliases()

        # Validate config against effective schema
        validated_app_config, errors = validate_config(config=app_config, schema=app_schema_effective)


        
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

    logger.info(f"App config loaded | key=%s | port=%s | problems=%d", key, controller.config_store.get('app', {}).get('daemon_http_port'), len(errors or {}))

    logger.debug(f'Controller.config_store: {controller.config_store}')
    controller.running = True

    daemon_http_port = controller.config_store.get('app', {}).get('daemon_http_port') or DAEMON_HTTP_PORT
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
