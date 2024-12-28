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

from constants import (
    DEFAULT_CONFIG_FILE,
    SCHEMA_FILE,
    CONFIG_FILE_DAEMON,
    CONFIG_FILE_USER,
    PID_FILE,
    LOG_FORMAT,
    DATE_FORMAT,
    PORT,
    ENV_PASS,
)

from library.base_plugin import BasePlugin


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
def load_yaml(path: Path) -> dict:
    """
    Helper to safely load YAML from path
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load YAML from {path}: {e}")
        return {}


def load_config(daemon_mode: bool = False) -> dict:
    """
    Load and merge YAML configurations:
    1. Load default config (baseline).
    2. Overlay with user/system config if it exists.
    """
    config = {
        'main': {}
    }

    # Load Default Config
    if DEFAULT_CONFIG_FILE.is_file():
        logger.info(f"Loading default config from: {DEFAULT_CONFIG_FILE}")
        config.update(load_yaml(DEFAULT_CONFIG_FILE))
    else:
        logger.warning("Default config not found. Proceeding without defaults.")


 
    # Load User/System Config
    config_path = CONFIG_FILE_DAEMON if daemon_mode else CONFIG_FILE_USER   

    if config_path.is_file():
        logger.info(f"Loading config file from: {config_path}")
        user_config = load_yaml(config_path)
        config.update(user_config)
    else:
        logger.info(f"No config file found at {config_path}. Using defaults.")

    return config


def validate_config(config: dict, schema: dict) -> dict:
    """Validate and fill in missing config values based on the schema."""
    validated_config = {}

    for section, section_schema in schema.items():
        validated_config[section] = {}
        for key, properties in section_schema.items():
            expected_type = properties['type']
            default_value = properties['default']
            allowed_values = properties.get('allowed', None)
            value_range = properties.get('range', None)
            required = properties.get('required', False)

            # Get the value from config or set to default
            value = config.get(section, {}).get(key, default_value)

            # Type-check and enforce the expected type
            if not isinstance(value, eval(expected_type)):
                if required:
                    raise ValueError(
                        f"Critical error: Invalid type for {section}.{key}. "
                        f"Expected {expected_type}, got {type(value).__name__}."
                    )
                logger.warning(
                    f"Invalid type for {section}.{key}. "
                    f"Expected {expected_type}, got {type(value).__name__}. "
                    f"Using default: {default_value}"
                )
                value = default_value

            # Range validation for int and float
            if value_range and isinstance(value, (int, float)):
                min_val, max_val = value_range
                if not (min_val <= value <= max_val):
                    if required:
                        raise ValueError(
                            f"Critical error: Value for {section}.{key} out of range. "
                            f"Expected between {min_val} and {max_val}, got {value}."
                        )
                    logger.warning(
                        f"Value for {section}.{key} out of range. "
                        f"Expected between {min_val} and {max_val}, got {value}. "
                        f"Using default: {default_value}"
                    )
                    value = default_value

            # Allowed values check
            if allowed_values and value not in allowed_values:
                if required:
                    raise ValueError(
                        f"Critical error: Invalid value for {section}.{key}. "
                        f"Allowed values: {allowed_values}, got: {value}."
                    )
                logger.warning(
                    f"Invalid value for {section}.{key}. "
                    f"Allowed values: {allowed_values}, got: {value}. "
                    f"Using default: {default_value}"
                )
                value = default_value

            validated_config[section][key] = value

    return validated_config


c = load_config()
s = load_yaml(SCHEMA_FILE)
validate_config(c, s)


# +
###############################################################################
# MAIN ENTRY POINT
###############################################################################

def main():
    # Register our signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Start the daemon loop in a background thread
    thread = threading.Thread(target=daemon_loop, daemon=True)
    thread.start()

    # Start Flask in the main thread (blocking call)
    logger.info(f"Starting Flask on port {PORT}...")
    # In production behind systemd, you might switch to gunicorn or uwsgi; for dev, this is fine.
    app.run(host="0.0.0.0", port=PORT, debug=False)


# -

if __name__ == "__main__":
    main()
