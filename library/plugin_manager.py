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
from pathlib import Path
import yaml
import logging
import uuid

try:
    from .exceptions import PluginError, ImageError, PluginTimeoutError, FileError, ConfigurationError
except ImportError:
    # support jupyter developement
    from exceptions import PluginError, ImageError, PluginTimeoutError, FileError, ConfigurationError
# -

logger = logging.getLogger(__name__)

# +
import logging
import sys

# Configure logging to show in Jupyter Notebook
def setup_notebook_logging(level=logging.DEBUG):
    log_format = '%(asctime)s [%(levelname)s] [%(name)s] - %(message)s'
    
    # Clear any existing handlers to prevent duplicate logging
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Set up logging for notebook
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    logging.getLogger(__name__).info("Notebook logging configured.")

# Run this cell to enable logging
setup_notebook_logging()

# +
import yaml
from pathlib import Path
import logging


class PluginManager:
    def __init__(
        self,
        config: dict = None,
        plugin_path: Path = None,
        config_path: Path = None,
        main_schema_file: str = None,
        plugin_schema_file: str = None,
    ):
        self.logger = logging.getLogger(__name__)
        self._config = {}
        self._configured_plugins = []        
        self.plugin_path = plugin_path
        self.config_path = config_path
        self.main_schema_file = main_schema_file
        self.plugin_schema_file = plugin_schema_file
        self._main_schema = None
        self._plugin_schema = None

        # Initialize config if provided
        if config:
            self.config = config

        self.logger.debug("PluginManager initialized with default values.")

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, value):
        if not isinstance(value, dict):
            raise TypeError("Config must be a dictionary.")
        
        schema = self.main_schema
        if schema:
            self.logger.info("Validating config against main schema...")
            self._validate_config(value, schema)

        self._config = value
        self.logger.info("Configuration successfully updated.")

    @property
    def config_path(self):
        return self._config_path

    @config_path.setter
    def config_path(self, value):
        if not value:
            self.logger.warning("Config path set to None. Schema loading disabled.")
            self._config_path = None
            return

        if not isinstance(value, Path):
            value = Path(value)

        if not value.is_dir():
            raise FileNotFoundError(f"Config directory not found at {value}")

        self._config_path = value
        self._main_schema = None
        self._plugin_schema = None
        self.logger.info(f"Config path set to {self._config_path}")

    @property
    def main_schema(self):
        if self._main_schema is None:
            if not self._config_path or not self.main_schema_file:
                self.logger.warning("Config path or main schema file not set.")
                return {}

            schema_file = self._config_path / self.main_schema_file
            if not schema_file.is_file():
                raise FileNotFoundError(f"Main schema file not found at {schema_file}")

            self.logger.info(f"Loading main config schema from {schema_file}")
            with open(schema_file, "r") as f:
                self._main_schema = yaml.safe_load(f)
        return self._main_schema

    @property
    def plugin_schema(self):
        if self._plugin_schema is None:
            if not self._config_path or not self.plugin_schema_file:
                self.logger.warning("Config path or plugin schema file not set.")
                return {}

            schema_file = self._config_path / self.plugin_schema_file
            if not schema_file.is_file():
                raise FileNotFoundError(f"Plugin schema file not found at {schema_file}")

            self.logger.info(f"Loading plugin schema from {schema_file}")
            with open(schema_file, "r") as f:
                self._plugin_schema = yaml.safe_load(f)
        return self._plugin_schema

    @property
    def configured_plugins(self):
        return self._configured_plugins

    @configured_plugins.setter
    def configured_plugins(self, value):
        if not isinstance(value, list):
            raise TypeError("configured_plugins must be a list of plugin configurations.")

        for plugin_entry in value:
            if not isinstance(plugin_entry, dict) or 'plugin' not in plugin_entry or 'config' not in plugin_entry:
                raise ValueError("Each entry in configured_plugins must be a dict with 'plugin' and 'config' keys.")

            
            # Always assign a new UUID (overwriting existing one)
            plugin_uuid = str(uuid.uuid4())[:8]
            plugin_entry['config']['uuid'] = plugin_uuid
            self.logger.info(f"Assigned UUID {plugin_entry['config']['uuid']} to plugin {plugin_entry['plugin']}.")
            
            # Validate the config against the plugin schema
            schema = self.plugin_schema.get('plugin_config', {})
            self._validate_config(plugin_entry['config'], schema)

            # final setup and validation
            if not plugin_entry.get('config', {}).get('name', None):
                name = plugin_entry.get('plugin') + '-' + plugin_uuid
                logger.info(f'No human readable plugin name set. Using: {name}')
                plugin_entry['config']['name'] = plugin_entry.get('plugin')
        
        self._configured_plugins = value
        self.logger.info("configured_plugins successfully validated and set.")
    
    def reload_schemas(self):
        """
        Force reload of main and plugin schemas.
        """
        self._main_schema = None
        self._plugin_schema = None
        self.logger.info("Schemas reloaded.")

    def _validate_config(self, config, schema):
        """
        Validate configuration against a schema.
        
        Args:
            config (dict): Configuration to validate.
            schema (dict): Schema to validate against.

        Raises:
            ValueError: If the config does not match the schema.
        """
        errors = []
        
        for key, params in schema.items():
            description = params.get('description', 'No description available')
            if key not in config:
                if params.get('required', False):
                    errors.append(f"{key} is required but missing. Description: {description}")
                else:
                    config[key] = params.get('default')
            else:
                value = config[key]
                expected_type = eval(params['type'])

                # Type check
                if not isinstance(value, expected_type):
                    errors.append(f"{key} must be of type {expected_type.__name__} (got {type(value).__name__}). Description: {description}")

                # Allowed values check
                allowed = params.get('allowed')
                if allowed and value not in allowed:
                    errors.append(f"{key} must be one of {allowed} (got {value}). Description: {description}")

        if errors:
            raise ValueError("Config validation failed:\n" + "\n".join(errors))

        self.logger.info("Config passed schema validation.")
# -

m = PluginManager()

# +
m.plugin_path = '../plugins/'
m.config_path = '../config/'
m.main_schema_file = 'main_schema.yaml'
m.plugin_schema_file = 'plugin_schema.yaml'

config = {
    'display_type': 'L',
    'resolution': (800, 480),
}
# -

configured_plugins = [
    {'plugin': 'basic_clock',
     'config': {
        'name': 'Basic Clock',
        'duration': 100,
        'refresh_interval': 60,
        'dormant': False,
        'layout': 'layout',
        'uuid': None
     }}
]
m.configured_plugins = configured_plugins

m.configured_plugins

# +

# self.update_function = self.default_update_function
# self.name = name
# self.duration = duration
# self.refresh_interval = refresh_interval
# self.plugin_timeout = plugin_timeout
# self.dormant = dormant
# self.last_updated = 0
# self.active = False
# self.resolution = resolution
# self.screen_mode = screen_mode
# self.force_onebit = force_onebit
# self.image = None
# self.config = config
# self.data = {}
# self.agent_string = "PaperPi"
# self.layout = layout
# self.update_data = None
# -

m.validate_config(m.config, m.plugin_manager_schema, 'base plugin schema')

m.plugin_path



# ## fix me!
#
# The code below should be used to load configuration from the user/system config and then use it to setup the plugin when it is created.
#


    def load_base_schema(self):
        """
        Load and validate base configuration using the global schema at 
        PaperPi/config/plugin_schema.yaml.
        
        Raises:
            PluginError: If base config fails critical validation.
        """
        schema_file = Path(self.base_config_path) / 'plugin_schema.yaml'
        logger.info(f'Loading base plugin schema: {schema_file}')

        if not schema_file.is_file():
            logger.error(f"Base schema {schema_file} missing. Cannot proceed.")
            raise FileError("Base schema is required but missing.")

        try:
            with open(schema_file, 'r') as f:
                schema = yaml.safe_load(f)

            base_schema = schema.get('base_config', {})
            if not base_schema:
                raise ConfigurationError(f'Error locating "base_config" section in {schema_file}')
            self.validate_schema(self.config, base_schema, "Base Config")

        except Exception as e:
            msg = f"{self.name} - Error loading base schema: {e}"
            logger.error(msg)
            raise PluginError(msg, plugin_name=self.name)

    def load_plugin_schema(self):
        """
        Load and validate plugin configuration using plugin_config.yaml
        in the plugin directory.
        
        Raises:
            PluginError: If plugin config fails validation.
        """
        schema_file = self.plugin_path / 'plugin_config.yaml'

        if not schema_file.is_file():
            logger.warning(f"{self.name} - plugin_config.yaml not found. Skipping plugin config validation.")
            return

        try:
            with open(schema_file, 'r') as f:
                schema = yaml.safe_load(f)

            plugin_schema = schema.get('plugin_config', {})
            # additional configuration is not required for plugins
            if plugin_schema:
                self.validate_schema(self.config, plugin_schema, "Plugin Config")
            else:
                pass

        except Exception as e:
            msg = f"{self.name} - Error loading plugin schema: {e}"
            logger.error(msg)
            raise PluginError(msg, plugin_name=self.name)

    def validate_schema(self, config, schema, schema_name):
        """
        Validate a configuration dictionary against a schema.

        Args:
            config (dict): Configuration to validate.
            schema (dict): Schema for validation.
            schema_name (str): Name of the schema for logging.

        Raises:
            PluginError: If required fields are missing or invalid.
        """
        for key, params in schema.items():
            # Apply defaults if missing
            if key not in config:
                config[key] = params.get('default')
                logger.info(f"{schema_name} - {key} set to default: {config[key]}")

            value = config[key]
            expected_type = eval(params['type'])

            # Type check
            if not isinstance(value, expected_type):
                msg = f"{schema_name} - {key} must be of type {expected_type}."
                logger.error(msg)
                raise PluginError(msg, plugin_name=self.name)

            # Allowed values
            allowed = params.get('allowed')
            if allowed and value not in allowed:
                msg = f"{schema_name} - {key} must be one of {allowed}."
                logger.error(msg)
                raise PluginError(msg, plugin_name=self.name)

            # Required field missing
            if params.get('required') and value is None:
                msg = f"{schema_name} - {key} is required but missing."
                logger.error(msg)
                raise PluginError(msg, plugin_name=self.name)

    def load_update_function(self):
        """
        Dynamically load the update_function from plugin.py in the plugin directory.
        Treats the plugin directory as a package to handle relative imports.
        """
        plugin_name = self.plugin_path.stem  # e.g., 'basic_clock'
        plugin_parent = str(self.plugin_path.parent)  # e.g., ../plugins
    
        if not (self.plugin_path / '__init__.py').is_file():
            msg = f"{plugin_name} - Missing __init__.py. Cannot load plugin as a package."
            logger.error(msg)
            raise PluginError(msg, plugin_name=self.name)
    
        try:
            # Add the parent directory to sys.path for package-level imports
            if plugin_parent not in sys.path:
                sys.path.insert(0, plugin_parent)
    
            # Import the plugin module dynamically as a package
            module = importlib.import_module(f"{plugin_name}.plugin")
    
            if hasattr(module, 'update_function'):
                self.update_function = module.update_function.__get__(self)
                logger.info(f"{plugin_name} - update_function successfully loaded.")
            else:
                msg = f"{plugin_name} - update_function not found in plugin.py"
                logger.error(msg)
                raise PluginError(msg, plugin_name=self.name)
    
        except Exception as e:
            msg = f"{plugin_name} - Failed to load update_function: {e}"
            logger.error(msg)
            raise PluginError(msg, plugin_name=self.name)

# +

    @property
    def plugin_path(self):
        return self._plugin_path

    @plugin_path.setter
    def plugin_path(self, value):
        if not value:
            self._plugin_path = None
            return
        
        if not isinstance(value, (str, Path)):
            raise TypeError('Must be of type str or Path')
        value = Path(value)
        if not value.is_dir():
            raise FileError('Plugin directory does not exist')

        self._plugin_path = value
        self.load_update_function()
    

