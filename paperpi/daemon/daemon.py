import logging
import sys
import json
import time
import threading
import signal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from paperpi.library.config_utils import validate_config, load_yaml_file, check_config_problems, make_json_safe
from paperpi.library.plugin_manager import PluginManager
from paperpi.constants import KEY_APPLICATION_SCHEMA, KEY_PLUGIN_DICT

logger = logging.getLogger(__name__)

class DaemonController:
    def __init__(self):
        self.running = True
        self.reload_requested = False
        self.config_store = {}
        self.server = None
        self.current_port = None
        self.http_api_running = False
        self.plugin_manager = PluginManager()

    def stop(self):
        self.running = False

    def request_reload(self):
        self.reload_requested = True

    def set_config(self, config: dict, scope: str = 'app'):
        self.config_store[scope] = config

    def get_config(self, scope: str = None):
        if not scope:
            logger.debug(self.config_store)
            return make_json_safe(self.config_store)
        else:
            return make_json_safe(self.config_store.get(scope, {}))

class DaemonRequestHandler(BaseHTTPRequestHandler):
    """
    Handles HTTP GET requests for the PaperPi daemon.
    """

    def do_GET(self):
        """
        Handle GET requests using a dynamic route dispatcher.
        """
        # Route /config/{scope} dynamically
        if self.path.startswith('/config'):
            self.handle_config_scope()
            return

        self.routes = {
            '/shutdown': self.handle_shutdown,
            '/reload': self.handle_reload,
            '/status': self.handle_status,
            '/check_config': self.handle_config_check,
            '/config': self.handle_config_scope,
            '/': self.handle_help,
        }

        handler_func = self.routes.get(self.path)
        if handler_func:
            handler_func()
        else:
            self.send_json({'error': 'Not found'}, status=404)

    def do_POST(self):
        """
        Handle POST requests using a dynamic route dispatcher.
        """
        self.routes_post = {
            '/config/check': self.handle_config_check,
        }

        handler_func = self.routes_post.get(self.path)
        if handler_func:
            handler_func()
        else:
            self.send_json({'error': 'Not found'}, status=404)    

    def handle_help(self):
        """
        Returns a JSON list of available HTTP endpoints and their descriptions.
        """
        help_data = []
        for path, handler in self.routes.items():
            doc = handler.__doc__.strip() if handler.__doc__ else "No description provided."
            help_data.append({
                "path": path,
                "description": doc
            })
        self.send_json(help_data)
        
    def handle_config_scope(self):
        """
        Returns configuration based on the scope in the path, like /config/app or /config/plugin_config. 
        The /config/ route returns all scopes.
        """
        path = self.path.strip('/')
        parts = path.split('/')
        logger.debug(f'Dynamically returning configuration based on path {path}; parts: {parts}')

        err_msg = None

        if len(parts) == 2 and parts[0] == 'config':
            scope = parts[1]
            config = self.server.controller.get_config(scope)
            if not config:
                err_msg = {'error': f'Scope "{scope}" not found'}
        elif len(parts) == 1 and parts[0] == 'config':
            scope = None
            config = self.server.controller.get_config()
            if not config:
                err_msg = {'error': 'No configuration found'}
        else:
            scope = None
            config = None
            err_msg = {'error': 'Invalid request'}

        if config:
            self.send_json(config)
        elif err_msg:
            self.send_json(err_msg, status=404)
        else:
            self.send_json({'error': 'Failed to execute request'}, status=404)

        # if len(parts) >= 3 and parts[1] == 'config':
        #     scope = parts[2]
        #     config = self.server.controller.get_config(scope)
        #     if config:
        #         self.send_json(config)
        #     else:
        #         self.send_json({'error': f'Scope "{scope}" not found'}, status=404)
        # elif len(parts) == 2 and parts[1] == 'config':
        #     config = self.server.controller.get_config()
        #     if config:
        #         self.send_json(config)
        #     else:
        #         self.send_json({'error': f'No configuration found!'}, status=404)
            
        # else:
        #     self.send_json({'error': 'Invalid config request'}, status=400)

    def handle_config_app(self):
        """
        Returns the application configuration as JSON.
        """
        self.send_json(self.server.controller.get_config())

    def handle_shutdown(self):
        """
        Triggers a graceful shutdown of the application.
        """
        self.send_json({'status': 'shutting down'})
        threading.Thread(target=handle_signal, args=(signal.SIGTERM, None, self.server.controller)).start()

    def handle_reload(self):
        """
        Reloads the configuration files and signals daemon to restart.
        """
        reload_config(self.server.controller)
        future_port = self.server.controller.get_config('app').get('daemon_http_port', None)
        self.send_json({
            'status': 'reloading configuration',
            'future_port': future_port
        })
        self.server.controller.request_reload()
        logger.info('Configuration reload requested.')

    def handle_status(self):
        """"
        Display basic status information
        """
        self.send_json({
            'running': self.server.controller.running,
            'app_config': self.server.controller.get_config('app'),
            'plugin_config': self.server.controller.get_config('plugin_config')
        })

    def handle_config_check(self):
        """
        Accepts a posted configuration dictionary and returns validation issues, if any.
        """
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        try:
            submitted_config = json.loads(post_data.decode('utf-8'))
        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON format.'}, status=400)
            return

        file_app_schema = self.server.controller.get_config('configuration_files').get('file_app_schema')
        try:
            schema = load_yaml_file(file_app_schema).get(KEY_APPLICATION_SCHEMA, {})
        except Exception as e:
            logger.error(f"Failed to load schema: {e}")
            self.send_json({'error': 'Failed to load schema.'}, status=500)
            return

        problems = check_config_problems(submitted_config, schema, strict=True)
        self.send_json({'problems': problems})


    def send_json(self, data, status=200):
        data_with_server_info = {
            "data": data,
            "server_info": {
                "current_port": self.server.controller.current_port
            }
        }
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data_with_server_info, indent=2).encode('utf-8'))



class DaemonHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, controller):
        super().__init__(server_address, RequestHandlerClass)
        self.controller = controller

def start_http_server(controller, port=8888):
    """
    Starts an HTTP server in a background thread to serve daemon data.
    """
    server = DaemonHTTPServer(('localhost', port), DaemonRequestHandler, controller)
    controller.server = server
    controller.current_port = port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Daemon HTTP server running at http://localhost:{port}")

def daemon_loop(controller):
    """
    The background thread that handles e-paper updates.
    It runs until controller.running is False or a reload is requested.
    """
    logger.info("Daemon loop started.")
    logger.debug(f"Daemon configuration store: {controller.config_store}")

    if not controller.http_api_running:
        start_http_server(controller=controller, port=controller.config_store['app']['daemon_http_port'])
        controller.http_api_running = True
    
    while controller.running:
        if controller.reload_requested:
            logger.info("Reload requested. Checking if HTTP API server needs restart...")
            new_port = controller.config_store['app']['daemon_http_port']
            if controller.current_port != new_port:
                logger.info(f"Port changed from {controller.current_port} to {new_port}. Restarting HTTP server.")
                if controller.server:
                    controller.server.shutdown()
                    controller.server.server_close()
                    controller.server = None
                start_http_server(controller=controller, port=new_port)
            else:
                logger.info("Port did not change; continuing with current HTTP server.")

            controller.reload_requested = False
            daemon_loop(controller)
            return
        logger.info("display update goes here")
        time.sleep(5)
    logger.info("Daemon loop stopped.")

def handle_signal(signum, frame, controller):
    """
    Handle SIGINT (Ctrl+C) or SIGTERM (systemctl stop) for a graceful shutdown:
    """
    logger.info(f"Signal {signum} received, initiating shutdown.")
    controller.stop()
    try:
        pass
    except Exception as e:
        logger.debug(f"Exception while shutting down web server: {e}")
    sys.exit(0)

def load_configuration(file_app_config: str | Path, 
                       file_app_schema: str | Path,
                       key_application_schema: str) -> dict:
    """
    Load and validate an application configuration against a schema.
    """
    file_app_config = Path(file_app_config)
    file_app_schema = Path(file_app_schema)

    try:
        logger.info('Reading application configuration')
        logger.debug(f'application config: {file_app_config}\napplication schema: {file_app_schema}')
        app_config_yaml = load_yaml_file(file_app_config)
        config_schema_yaml = load_yaml_file(file_app_schema)

    except FileNotFoundError as e:
        logger.error(f'Failed to read one or more configuration files: {e}')
        raise FileNotFoundError(e)
    except ValueError as e:
        logger.error(f'Invalid configuration file: {e}')
        raise ValueError(e)

    try:
        logger.info('Validating application configuration')
        logger.debug(file_app_config)
        app_config_yaml = app_config_yaml.get(key_application_schema, None)
        config_schema_yaml = config_schema_yaml.get(key_application_schema, None)

        missing = []
        if not app_config_yaml:
            missing.append(file_app_config)
        if not config_schema_yaml:
            missing.append(file_app_schema)

        if missing:
            raise ValueError(f'the following files are missing the section "{key_application_schema}": {missing}')
        
        app_configuration = validate_config(app_config_yaml, config_schema_yaml)
    except (TypeError, ValueError) as e:
        logger.error(f'Failed to validate configuration in {file_app_config}: {e}')
        raise ValueError(e)

    return app_configuration

def reload_config(controller):
    logger.info('Reloading configuration files')
    file_app_config = controller.get_config('configuration_files').get('file_app_config', None)
    file_app_schema = controller.get_config('configuration_files').get('file_app_schema', None)
    try:
        app_configuration = load_configuration(
            file_app_config=file_app_config,
            file_app_schema=file_app_schema, 
            key_application_schema=KEY_APPLICATION_SCHEMA
        )
    except (TypeError, ValueError) as e:
        logger.error(f'Failed to load configuration files: {e}')
        logger.error(f'Shutting down daemon')
        controller.stop()
        return

    logger.info('Setting up PluginManager')
    controller.set_config(app_configuration, scope='app')
    # controller.set_config({}, scope='plugin_config')
    file_pluginmanager_schema = controller.get_config('configuration_files').get('file_pluginmanager_schema')
    file_plugin_schema = controller.get_config('configuration_files').get('file_plugin_schema')
    key_plugin_dict = controller.get_config('configuration_files').get('key_plugin_dict')
    path_app_plugins = controller.get_config('configuration_files').get('path_app_plugins')
    path_config = Path(file_plugin_schema).parent

    try:
        plugin_configuration = load_yaml_file(file_plugin_config)
        logger.debug(f'plugin_configuration: {plugin_configuration}')
    except (FileNotFoundError, ValueError) as e:
        logger.error(f'Failed to load plugin configuration file: {e}')
        logger.error('Shutting down daemon due to invalid plugin configuration.')
        controller.stop()
        return

    controller.set_config(plugin_configuration, scope='plugin_config')

    controller.plugin_manager = PluginManager(
        plugin_path=path_app_plugins,
        config_path=path_config,
        base_schema_file=file_pluginmanager_schema,
        plugin_schema_file=file_plugin_schema
    )
    

