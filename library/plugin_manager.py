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
class PluginManager:
    def __init__(
        self,
        config: dict={},
        plugin_path: Path=None,
        base_config_path: Path=None
    ):
        """
        Initialize the PluginManager.
    
        Args:
            config (dict): Dictionary containing plugin configuration.
            plugin_path (Path): Path to the directory containing plugins.
            base_config_path (Path): Path to base configuration schema for validation.
        """
        # Create a logger for this class/module
        logger.debug("PluginManager instance created.")        
        self._base_schema = None
        self.config = config
        self.plugin_path = plugin_path
        self.base_config_path = base_config_path
        self.active_plugins = []
        self.dormant_plugins = []

    @property
    def base_config_path(self):
        return self._base_config_path

    @base_config_path.setter
    def base_config_path(self, value):
        if not value:
            raise ValueError("base_config_path cannot be empty.")
            
        if not isinstance(value, Path):
            value = Path(value)

        if not value.is_file():
            raise FileNotFoundError(f"Schema file not found at {value}")

        self._base_config_path = value
        # Invalidate cached schema to trigger reload
        self._base_schema = None 

    @property
    def base_schema(self):
        if self._base_schema is None:
            logger.info(f"Loading base config schema from {self._base_config_path}")
            with open(self._base_config_path, 'r') as f:
                self._base_schema = yaml.safe_load(f)
        return self._base_schema
    

# -

m = PluginManager(
    config={}, 
    plugin_path='../plugins', 
    base_config_path='../config/plugin_schema.yaml')



m.base_schema

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
    

