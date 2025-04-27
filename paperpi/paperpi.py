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

import uvicorn


from paperpi.constants import * 

# from library.base_plugin import BasePlugin
from paperpi.library.config_utils import validate_config, load_yaml_file, write_yaml_file
from paperpi.library.plugin_manager import PluginManager
from paperpi.daemon.daemon import DaemonController, daemon_loop, load_configuration
from paperpi.logging_setup import setup_logging


logger = setup_logging()


def running_under_systemd():
    """
    A simple heuristic to detect if we're running under systemd.
    If these environment variables are present, systemd likely launched us.
    """
    return ('INVOCATION_ID' in os.environ) or ('JOURNAL_STREAM' in os.environ)


# -

def parse_args():

    # detect jupyter's ipykernel_launcher and trim the jupyter args
    if 'ipykernel_launcher' in sys.argv[0]:
        argv = sys.argv[3:]
    else:
        argv = sys.argv[1:]
        
    parser = argparse.ArgumentParser(description="PaperPi App")
    parser.add_argument("-d", "--daemon", action="store_true",
                        help="Run in daemon mode (use system-wide config)")

    parser.add_argument("-c", "--config", type=str, default=None,
                         help="Path to application configuration yaml file")

    parser.add_argument("-p", "--plugin_config", type=str, default=None,
                          help="Path to plugin configuration yaml file")
    
    parser.add_argument(
        "-l", "--log_level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="WARNING",
        help="Logging output level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
)

    return parser.parse_args(argv)


def cleanup(msg: str = None):
    if msg:
        print(msg)

    sys.exit(0)


def main():
    controller = DaemonController()

    # Register our signal handlers
    signal.signal(signal.SIGINT, lambda s, f: controller.stop())
    signal.signal(signal.SIGTERM, lambda s, f: controller.stop())

    args = parse_args()

    # set logging level immediately to default or command line value
    if args.log_level:
        logger.setLevel(args.log_level)
        log_level = args.log_level
        log_override = True
        logging.info(f'Default logging set at command line to: {log_level}')
    else:
        logger.setLevel(LOG_LEVEL)
        log_level = LOG_LEVEL
        log_override = False
    
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

    file_plugin_schema = PATH_APP_CONFIG / FNAME_PLUGIN_SCHEMA

    file_pluginmanager_schema = PATH_APP_CONFIG / FNAME_PLUGIN_MANAGER_SCHEMA
    
    key_plugin_dict = KEY_PLUGIN_DICT

    file_daemon_pid = PATH_PID / FILENAME_PID

    path_app_plugins = PATH_APP_PLUGINS


    configuration_files = {
        'file_app_config': file_app_config,
        'file_plugin_config': file_plugin_config,
        'file_app_schema': file_app_schema,
        'key_application_schema': KEY_APPLICATION_SCHEMA,
        'file_plugin_schema': file_plugin_schema,
        'file_pluginmanager_schema': file_pluginmanager_schema,
        'key_plugin_dict': key_plugin_dict,
        'file_daemon_pid': file_daemon_pid,
        'path_app_plugins': path_app_config

    }
    
    # load the application configuration 
    try:
        app_configuration = load_configuration(file_app_config, file_app_schema, KEY_APPLICATION_SCHEMA)
    except (ValueError, FileNotFoundError) as e:
        cleanup(f'Failed to load configuration: {e}')    

    # set to configuration file logging level if not set on the command line
    if not log_override:
        logger.setLevel(app_configuration.get('log_level', LOG_LEVEL))
    else:
        app_configuration['log_level'] = log_level

    controller.set_config(app_configuration, scope='app')
    controller.set_config(configuration_files, scope='configuration_files')

    # Start the daemon loop in a dedicated thread after setting config
    daemon_thread = threading.Thread(target=daemon_loop, args=(controller,), daemon=True)
    daemon_thread.start()
    daemon_thread.join()

    logger.info('Cleaning up...')
# +
test_args = [
             # ('-d', None), 
             #('-c', '~/.config/com.txoof.paperpi/paperpi_config.yaml'), 
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
print("ARGV ARE:")
print(sys.argv) 
# -

sys.argv

if __name__ == "__main__":
    main()
