# constants.py
from pathlib import Path

### Paths
# Default Config File
DEFAULT_CONFIG_FILE = Path(__file__).parent / "config" / "paperpi_config.yaml"
# Schema file
SCHEMA_FILE = Path(__file__).parent / "config" / "paperpi_config_schema.yaml"
# PID for daemon mode
PID_FILE = "/tmp/paperpi_daemon.pid"
# Location of user on-demand files
CONFIG_FILE_USER = Path("~/.config.com.txoof/paperpi/paperpi_config.yaml")
# Location of daemon config files
CONFIG_FILE_DAEMON = Path("/etc/paperpi/paperpi_config.yaml")

### Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

### Environment Keys
ENV_PASS = "PAPERPI_PASS"

### Web Interface
PORT = 2693

