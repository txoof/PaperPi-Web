#!/usr/bin/env python
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

# %load_ext autoreload
# %autoreload 2
# +
import sys
import argparse
import logging
import threading
import time
import signal
import os
import yaml
from pathlib import Path

from flask import Flask, jsonify, request

from constants import * 

# from library.base_plugin import BasePlugin
from library.plugin_manager import PluginManager


# +
# ###############################################################################
# # LOGGING CONFIGURATION
# ###############################################################################

def running_under_systemd():
    """
    A simple heuristic to detect if we're running under systemd.
    If these environment variables are present, systemd likely launched us.
    """
    return ('INVOCATION_ID' in os.environ) or ('JOURNAL_STREAM' in os.environ)


# # Configure the main logger
# logger = logging.getLogger("PaperPi")
# logger.setLevel(logging.INFO)

# # Avoid adding duplicate handlers
# if not logger.hasHandlers():
#     handler = logging.StreamHandler(sys.stdout)
#     formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
#     handler.setFormatter(formatter)
#     logger.addHandler(handler)

#     if running_under_systemd():
#         try:
#             from systemd.journal import JournalHandler
#             handler = JournalHandler()
#         except ImportError:
#             handler = logging.StreamHandler()
#     else:
#         handler = logging.StreamHandler()

#     formatter = logging.Formatter(
#         fmt='%(asctime)s [%(levelname)s] %(message)s',
#         datefmt='%Y-%m-%d %H:%M:%S'
#     )
#     handler.setFormatter(formatter)
#     logger.addHandler(handler)

# # Plugin Manager Logger
# plugin_manager_logger = logging.getLogger("library.plugin_manager")
# plugin_manager_logger.setLevel(logging.INFO)
# plugin_manager_logger.propagate = True

# +
def setup_logging(level=logging.INFO):
    # Set up the root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create a console handler
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)
    
    # Attach the handler to the root logger
    logger.addHandler(handler)

    # Test logging from the main program
    logger.info("Logger setup complete. Ready to capture logs.")
    
    # Test logging from a simulated library
    library_logger = logging.getLogger("library.plugin_manager")

    return logger

logger = setup_logging()

# +
###############################################################################
# FLASK WEB SERVER
###############################################################################

app = Flask(__name__)

# We'll store a flag indicating the daemon loop is running
daemon_running = True
# We'll also detect if we're in systemd mode or foreground
systemd_mode = running_under_systemd()

@app.route('/')
def home():
    return """
    <h1>Welcome to PaperPi</h1>
    <p>Stub login page or config interface will go here.</p>
    <p>Try POSTing to /stop to halt the daemon.</p>
    """

@app.route('/login')
def login():
    # Stub route for future authentication implementation
    return "Login page (to be implemented)."

@app.route('/stop', methods=['POST'])
def stop_route():
    """
    A web endpoint to stop the daemon thread (and Flask).
    In systemd mode, the service will stop in the background.
    In foreground mode, we print 'stopped: press ctrl+c to exit.'
    """
    global daemon_running
    daemon_running = False
    logger.info("Received /stop request; shutting down daemon and Flask...")

    # Ask Flask's built-in server to shut down
    shutdown_server()

    if not systemd_mode:
        # In foreground mode, let the user know they can Ctrl+C
        logger.info("stopped: press ctrl+c to exit")

    return jsonify({"message": "Stopping daemon..."})

def shutdown_server():
    """
    Trigger a shutdown of the built-in Werkzeug server.
    """
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        logger.warning("Not running with the Werkzeug Server, can't shut down cleanly.")
    else:
        func()


# +
###############################################################################
# DAEMON LOOP
###############################################################################

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


# +
###############################################################################
# SIGNAL HANDLING
###############################################################################

def handle_signal(signum, frame):
    """
    Handle SIGINT (Ctrl+C) or SIGTERM (systemctl stop) for a graceful shutdown:
      - Stop the daemon loop
      - Shut down Flask if possible
    """
    logger.info(f"Signal {signum} received, initiating shutdown.")
    global daemon_running
    daemon_running = False

    # Attempt to stop the Flask server
    # (If running under systemd or a non-Werkzeug server, it might just exit the main thread.)
    try:
        shutdown_server()
    except Exception as e:
        logger.debug(f"Exception while shutting down Flask: {e}")

    # If running in the foreground, user can also press Ctrl+C again, but let's exit gracefully
    sys.exit(0)


# -

###############################################################################
# ARGUMENT PARSING
###############################################################################
def parse_args():

    # detect jupyter's ipykernel_launcher and trim the jupyter args
    if 'ipykernel_launcher' in sys.argv[0]:
        argv = sys.argv[3:]
    else:
        argv = sys.argv
        
    parser = argparse.ArgumentParser(description="PaperPi App")
    parser.add_argument("-d", "--daemon", action="store_true",
                        help="Run in daemon mode (use system-wide config)")

    parser.add_argument("-c", "--config", type=str, default=None,
                         help="Path to application configuration yaml file")

    parser.add_argument("-p", "--plugin_config", type=str, default=None,
                          help="Path to plugin configuration yaml file")
    
    return parser.parse_args(argv)


###############################################################################
# CONFIG LOADING
###############################################################################
def load_yaml_file(filepath: str) -> dict:
    """
    Safely load a YAML file and return its contents as a dictionary.

    Args:
        filepath (str): Path to the YAML file.

    Returns:
        dict: Parsed contents of the YAML file.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the file cannot be parsed or is not a dictionary.
    """
    path = Path(filepath).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")

    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML file '{path}': {e}")

    if not isinstance(data, dict):
        raise ValueError(f"YAML file '{path}' does not contain a valid dictionary.")

    logger.info(f"YAML file '{path}' loaded successfully.")
    return data


def load_yaml_file(filepath: str) -> dict:
    """
    Safely load a YAML file and return its contents as a dictionary.

    Args:
        filepath (str): Path to the YAML file.

    Returns:
        dict: Parsed contents of the YAML file.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the file cannot be parsed or is not a dictionary.
    """
    path = Path(filepath).expanduser().resolve()

    logger.info(F"Reading yaml file at {path}")

    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")

    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML file '{path}': {e}")

    if not isinstance(data, dict):
        raise ValueError(f"YAML file '{path}' does not contain a valid dictionary.")

    logger.info(f"YAML file '{path}' loaded successfully.")
    return data


def write_yaml_file(filepath: str, data: list) -> bool:
    """
    Write a list of dictionaries to a YAML file.

    Args:
        filepath (str): The path to the YAML file.
        data (list): List of dictionaries to convert to YAML.

    Returns:
        bool: True if the file was written successfully, False otherwise.

    Raises:
        FileNotFoundError: If the parent directory of the filepath does not exist.
    """
    filepath = Path(filepath).expanduser().resolve()

    # Check if the parent directory exists
    if not filepath.parent.exists():
        raise FileNotFoundError(f"Directory does not exist: {filepath.parent}")
    
    try:
        # Write to file
        with open(filepath, 'w') as file:
            yaml.dump(data, file, default_flow_style=False, sort_keys=False)
        
        print(f"YAML file successfully written to {filepath}")
        return True
    
    except Exception as e:
        print(f"Failed to write YAML file: {e}")
        return False


def load_validate_config(config_file: Path, schema_file: Path, section_key: str = None):
    """
    Load and validate a configuration file against a schema.

    Args:
        config_file (Path): Path to the configuration YAML file.
        schema_file (Path): Path to the schema YAML file.
        section_key (str, optional): Key for a specific section of the config to validate.

    Returns:
        tuple:
            dict: Parsed and validated configuration (empty if errors occur).
            dict: Errors categorized into 'fatal', 'recoverable', and 'other'.
    """
    def safe_yaml_load(file_path: Path) -> dict:
        try:
            return load_yaml_file(file_path)
        except Exception as e:
            msg = f"Failed to load {file_path} due error {e}"
            logger.error(msg)
            errors.append(msg)
            return {}

    config = {}
    errors = []

    logger.info(f"Loading configuration from: {config_file.resolve()}")
    logger.info(f"Loading schema from: {schema_file.resolve()}")

    schema_dict = safe_yaml_load(schema_file)
    config_dict = safe_yaml_load(config_file)

    if not schema_dict or not config_dict:
        msg = "Critical error loading schema or configuration file"
        logger.error(msg)
        errors.append(msg)
        return config, errors

    logger.info("Validating configuration against schema...")

    if section_key:
        config_section = config_dict.get(section_key)
        schema_section = schema_dict.get(section_key)
    else:
        config_section = config_dict
        schema_section = schema_dict

    try:
        config = PluginManager.validate_config(config_section, schema_section)
        logger.info(f"Configuration validated successfully")
    except Exception as e:
        msg = f"Validation failed {e}"
        errors.append(msg)
        return config, errors

    return config, errors


# +
args = parse_args()


if running_under_systemd() or args.daemon:
    # configuration file in daemon mode
    file_app_config = PATH_DAEMON_CONFIG / FNAME_APPLICATION_CONFIG
else:
    # configuration in user on-demand mode
    file_app_config = PATH_USER_CONFIG / FNAME_APPLICATION_CONFIG

# apply override from command line
if args.config:
    file_app_config = Path(args.config)


# get the parent dir of the application configuration file 
path_app_config = file_app_config.parent

# use the supplied plugin_config_file
if args.plugin_config:
    file_plugin_config = Path(args.plugin_config)
# otherwise use the default
else:
    file_plugin_config = path_app_config / FNAME_PLUGIN_CONFIG


# validate the application configuration
app_configuration, errors = load_validate_config(file_app_config, 
                                                 PATH_APP_CONFIG / FNAME_APPLICATION_SCHEMA,
                                                 KEY_APPLICATION_SCHEMA)
                                                 

# get the resolution & screenmode from the configured epaper driver
resolution = (800, 640)
screen_mode = 'L'
app_configuration['resolution'] = resolution
app_configuration['screen_mode'] = screen_mode


# load the plugin configuration; validation will happen in the plugin manager
plugin_configuration = load_yaml_file(file_plugin_config)

# build the plugin manager 
plugin_manager = PluginManager()
# -

plugin_manager.plugin_path = PATH_APP_PLUGINS
plugin_manager.config_path = PATH_APP_CONFIG
plugin_manager.base_schema_file = FNAME_PLUGIN_MANAGER_SCHEMA
plugin_manager.plugin_schema_file = FNAME_PLUGIN_SCHEMA
try:
    plugin_manager.config = app_configuration
except ValueError as e:
    msg = f"Configuration file error: {e}"
    logger.error(msg)
    # do something to bail out and stop loading here


plugin_manager.add_plugins(plugin_configuration[KEY_PLUGIN_DICT])


plugin_manager.configured_plugins


# +
###############################################################################
# MAIN ENTRY POINT
###############################################################################

def main():
    # Register our signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # load applicaiton configuration
    # app_config, errors = load_application_config()

    

    if len(errors.get('fatal'), 0) > 0:
        logger.error("Fatal errors occured during configuration load:")
        for e in errors:
            logger.error(f"{e}")
            print(e)

    web_port = app_config.get('port', constants.PORT)
    log_level = app_config.get('log_level', logging.WARNING)

    logger.setLevel(log_level)

    
    
    # # Start the daemon loop in a background thread
    # thread = threading.Thread(target=daemon_loop, daemon=True)
    # thread.start()

    # # Start Flask in the main thread (blocking call)
    # logger.info(f"Starting Flask on port {web_port}...")
    # # In production behind systemd, you might switch to gunicorn or uwsgi; for dev, this is fine.
    # app.run(host="0.0.0.0", port=PORT, debug=False)
# -

app_configuration[0]



# +
test_args = [
             # ('-d', None), 
             ('-c', '~/.config/com.txoof.paperpi/paperppi.yaml'), 
             # ('-p', '~/.config/com.txoof.paperpi/plugins_config.yaml')
            ]

for key, value in test_args:
    try:
        idx = sys.argv.index(key)
        if value is not None:
            # Check if the next argument exists and update it
            if idx + 1 < len(sys.argv):
                sys.argv[idx + 1] = value
            else:
                # If no value exists, append it
                sys.argv.append(value)
    except ValueError:
        # If key is not in sys.argv, add it along with the value (if applicable)
        sys.argv.append(key)
        if value is not None:
            sys.argv.append(value)
        
print(sys.argv) 
# -

sys.argv

if __name__ == "__main__":
    main()
