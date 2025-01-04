# constants.py
from pathlib import Path

### Paths
CONFIG_PATH = Path(__file__).parent / "config"

# Default Config File
DEFAULT_CONFIG_FILE = CONFIG_PATH / "paperpi_config.yaml"

# Application schema file
APPLICATION_SCHEMA = CONFIG_PATH / "paperpi_config_schema.yaml"
APPLICATION_SCHEMA_KEY = 'main'

# Plugin manager schema
PLUGIN_MANAGER_SCHEMA = CONFIG_PATH / "plugin_manager_schema.yaml"


# Basic plugin schema
PLUGIN_SCHEMA = CONFIG_PATH / "plugin_schema.yaml"

# PID for daemon mode
PID_FILE = "/tmp/paperpi_daemon.pid"

# Configuration file names
APPLICATION_CONFIG = 'paperpi_config.yaml'
PLUGIN_CONFIG = 'paperpi_plugins.yaml'

# Location of user on-demand mode files
CONFIG_ROOT_USER = Path("~/.config/com.txoof.paperpi")
CONFIG_FILE_USER = CONFIG_ROOT_USER / APPLICATION_CONFIG
PLUGIN_CONFIG_USER = CONFIG_ROOT_USER / PLUGIN_CONFIG


# Location of daemon mode config files
CONFIG_ROOT_DAEMON = Path("/etc/paperpi")
CONFIG_FILE_DAEMON = CONFIG_ROOT_DAEMON / APPLICATION_CONFIG
PLUGIN_CONFIG_DAEMON = CONFIG_ROOT_DAEMON


### Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

### Environment Keys
ENV_PASS = "PAPERPI_PASS"

### Web Interface
PORT = 2693

