# constants.py
from pathlib import Path

### Paths
PATH_APP_CONFIG = Path(__file__).parent / "config"
PATH_APP_PLUGINS = Path(__file__).parent / "plugins"
PATH_DAEMON_CONFIG = Path("/etc/paperpi/")
PATH_USER_CONFIG = Path("~/.config/com.txoof.paperpi/").expanduser().resolve()
PATH_PID = Path("/tmp/")



# Files
FNAME_PLUGIN_MANAGER_SCHEMA = "plugin_manager_schema.yaml"
FNAME_PLUGIN_SCHEMA = "plugin_base_schema.yaml"
FNAME_APPLICATION_SCHEMA = "paperpi_config_schema.yaml"

FNAME_APPLICATION_CONFIG = "paperpi_config.yaml"
FNAME_PLUGIN_CONFIG = "paperpi_plugins.yaml"

# Dict keys
KEY_APPLICATION_SCHEMA = 'main'
KEY_PLUGIN_DICT = 'plugins'

# PID for daemon mode
FILENAME_PID = "paperpi_daemon.pid"


# # Location of user on-demand mode files
# CONFIG_ROOT_USER = Path("~/.config/com.txoof.paperpi")
# CONFIG_FILE_USER = CONFIG_ROOT_USER / APPLICATION_CONFIG
# PLUGIN_CONFIG_USER = CONFIG_ROOT_USER / PLUGIN_CONFIG


# # Location of daemon mode config files
# CONFIG_ROOT_DAEMON = Path("/etc/paperpi")
# CONFIG_FILE_DAEMON = CONFIG_ROOT_DAEMON / APPLICATION_CONFIG
# PLUGIN_CONFIG_DAEMON = CONFIG_ROOT_DAEMON




### Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = "WARNING"

### Environment Keys
ENV_PASS = "PAPERPI_PASS"

### API and Web Interface Ports
WEB_PORT = 2820
DAEMON_HTTP_PORT = 2822
