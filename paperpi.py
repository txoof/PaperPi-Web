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
from pathlib import Path

from constants import * 

# from library.base_plugin import BasePlugin
from library.config_utils import validate_config, load_yaml_file, write_yaml_file
from library.plugin_manager import PluginManager
from daemon.daemon import daemon_loop
from logging_setup import setup_logging
# -

logger = setup_logging()

# +
# # ###############################################################################
# # # LOGGING CONFIGURATION
# # ###############################################################################

# def running_under_systemd():
#     """
#     A simple heuristic to detect if we're running under systemd.
#     If these environment variables are present, systemd likely launched us.
#     """
#     return ('INVOCATION_ID' in os.environ) or ('JOURNAL_STREAM' in os.environ)


# +
# def setup_logging(level=logging.INFO):
#     # Set up the root logger
#     logger = logging.getLogger()
#     logger.setLevel(level)

#     # Remove existing handlers to avoid duplicates
#     if logger.hasHandlers():
#         logger.handlers.clear()

#     # Create a console handler
#     handler = logging.StreamHandler(sys.stdout)
#     formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
#     handler.setFormatter(formatter)
    
#     # Attach the handler to the root logger
#     logger.addHandler(handler)

#     # Test logging from the main program
#     logger.info("Logger setup complete. Ready to capture logs.")
    
#     # Test logging from a simulated library
#     library_logger = logging.getLogger("library.plugin_manager")

#     return logger

# logger = setup_logging()

# +
# ###############################################################################
# # SIGNAL HANDLING
# ###############################################################################

# def handle_signal(signum, frame):
#     """
#     Handle SIGINT (Ctrl+C) or SIGTERM (systemctl stop) for a graceful shutdown:
#       - Stop the daemon loop
#       - Shut down Flask if possible
#     """
#     logger.info(f"Signal {signum} received, initiating shutdown.")
#     global daemon_running
#     daemon_running = False

    
#     # shtudown web server here
#     try:
#         pass # shutdown 
#     except Exception as e:
#         logger.debug(f"Exception while shutting down Flask: {e}")

#     # If running in the foreground, user can also press Ctrl+C again, but let's exit gracefully
#     sys.exit(0)
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


def cleanup(msg: str = None):
    if msg:
        print(msg)

    sys.exit(0)


# +
###############################################################################
# MAIN ENTRY POINT
###############################################################################

def main():
    # Register our signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

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
    
    file_app_schema = PATH_APP_CONFIG / FNAME_APPLICATION_SCHEMA

    try:
        app_config_yaml = load_yaml_file(file_app_config)
        config_schema_yaml = load_yaml_file(file_app_schema)

        # add plugin schema and plugin manager schema here
        
    except (FileNotFoundError, ValueError) as e:
        logger.error(f'Failed to read configuration files: {e}')
        cleanup()
        
 
    try:
        logger.info('Validating application configuration')
        logger.debug(file_app_config)
        app_configuration = validate_config(app_config_yaml[KEY_APPLICATION_SCHEMA], config_schema_yaml)
    except ValueError as e:
        logger.error(f'Failed to validate configuration in {file_app_config}')
        cleanup()
    
    
    # get the web port and log level
    web_port = app_configuration.get('port', PORT)
    log_level = app_configuration.get('log_level', logging.WARNING)
    
    
    # get the resolution & screenmode from the configured epaper driver

    ### hard coded for the moment
    resolution = (800, 640)
    screen_mode = 'L'
    
    app_configuration['resolution'] = resolution
    app_configuration['screen_mode'] = screen_mode
    
    
    # load the plugin configuration; validation will happen in the plugin manager
    plugin_configuration = load_yaml_file(file_plugin_config)
    
    # build the plugin manager 
    plugin_manager = PluginManager()
    
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
        
    # add the plugins based on the loaded configurations
    plugin_manager.add_plugins(plugin_configuration[KEY_PLUGIN_DICT])
    # validate and load the plugins
    plugin_manager.load_plugins()



    
    
    # # Start the daemon loop in a background thread
    # thread = threading.Thread(target=daemon_loop, daemon=True)
    # thread.start()

    # # Start Flask in the main thread (blocking call)
    # logger.info(f"Starting Flask on port {web_port}...")
    # # In production behind systemd, you might switch to gunicorn or uwsgi; for dev, this is fine.
    # app.run(host="0.0.0.0", port=PORT, debug=False)
# +
test_args = [
             # ('-d', None), 
             ('-c', '~/.config/com.txoof.paperpi/paperpi_config.yaml'), 
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


