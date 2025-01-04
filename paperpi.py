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

# +
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

import constants

# from library.base_plugin import BasePlugin
from library.plugin_manager import PluginManager


# +
###############################################################################
# LOGGING CONFIGURATION
###############################################################################

def running_under_systemd():
    """
    A simple heuristic to detect if we're running under systemd.
    If these environment variables are present, systemd likely launched us.
    """
    return ('INVOCATION_ID' in os.environ) or ('JOURNAL_STREAM' in os.environ)

logger = logging.getLogger("PaperPi")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
handler.setFormatter(formatter)
logger.addHandler(handler)

if running_under_systemd():
    # Log to the systemd journal so entries appear in 'journalctl -u <service>'
    try:
        from systemd.journal import JournalHandler
        handler = JournalHandler()
    except ImportError:
        # If python-systemd is not installed, fallback to console logging
        handler = logging.StreamHandler()
else:
    # If running directly, log to console
    handler = logging.StreamHandler()

formatter = logging.Formatter(
    fmt='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

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
    parser = argparse.ArgumentParser(description="PaperPi App")
    parser.add_argument("-d", "--daemon", action="store_true",
                        help="Run in daemon mode (use system-wide config)")
    return parser.parse_args()


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


load_validate_config(constants.CONFIG_FILE_USER, constants.APPLICATION_SCHEMA, constants.APPLICATION_SCHEMA_KEY)



def load_application_config(daemon_mode: bool = False) -> tuple:
    """
    Load and validate application configuration and merge with default config for
    missing values

    Args:
        daemon_mode (bool): Select system config when true, select user config when false
        
    Returns:
        dict: Parsed and validated configuration
    """
    config = {}
    errors = {'fatal': [],
              'recoverable': [],
              'other': [],}
    if daemon_mode:
        application_config = constants.CONFIG_FILE_DAEMON
    else:
        application_config = constants.CONFIG_FILE_USER

    logger.info(f"Application mode: {'Daemon' if daemon_mode else 'User'}. Loading configuration from {application_config}")
    try:
        schema_dict = load_yaml_file(constants.APPLICATION_SCHEMA)
    except Exception as e:
        msg = f"Failed to load schema from {constants.APPLICATION_SCHEMA} due to errors: {e}"
        logger.error(msg)
        errors['fatal'].append(msg)
        schema_dict = {}
        
    try:
        config_dict = load_yaml_file(application_config)
    except Exception as e:
        msg = f"Failed to load configuraiton from {application_config} due to errors: {e}"
        logger.error(msg)
        errors['fatal'].append(msg)
        config_dict = {}

    logger.info("Validating application configuration against schema")

    # return config_dict, schema_dict
    if len(errors.get('fatal', 0)) == 0:
        try:
            config = PluginManager.validate_config(config_dict.get(constants.APPLICATION_SCHEMA_KEY), 
                                                             schema_dict.get(constants.APPLICATION_SCHEMA_KEY))
        except ValueError as e:
            msg = f"Failed to validate configuration due "
            validated_config = {}
    else:
        logger.warning(f"Skipping validation due to previous fatal errors")            
        
            
    return config, errors


def load_plugin_config(daemon_mode: bool = False ) -> tuple:


# +
###############################################################################
# MAIN ENTRY POINT
###############################################################################

def main():
    # Register our signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # load applicaiton configuration
    app_config, errors = load_application_config()

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

if __name__ == "__main__":
    main()


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


s = load_yaml_file('./config/paperpi_config_schema.yaml')
c = load_yaml_file('~/.config/com.txoof.paperpi/paperpi_config.yaml')

s['main']

c['main']['vcom'] = -1.90

vc = validate_config(c['main'], s['main'])
vc


