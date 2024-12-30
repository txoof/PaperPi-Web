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
from pathlib import Path
import yaml
import logging
import uuid
from importlib import import_module


try:
    from .exceptions import PluginError, ImageError, PluginTimeoutError, FileError, ConfigurationError
    from .base_plugin import BasePlugin
except ImportError:
    # support jupyter developement
    from exceptions import PluginError, ImageError, PluginTimeoutError, FileError, ConfigurationError
    from base_plugin import BasePlugin
# -

logger = logging.getLogger(__name__)


# +
# Configure logging to show in Jupyter Notebook with detailed output
def setup_notebook_logging(level=logging.DEBUG):
    log_format = (
        '%(asctime)s [%(levelname)s] [%(name)s] '
        '[%(module)s.%(funcName)s] [%(lineno)d] - %(message)s'
    )
    
    # Clear any existing handlers to prevent duplicate logging
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Set up logging for notebook
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    logging.getLogger(__name__).debug("Notebook logging configured.")

# Run this cell to enable logging
setup_notebook_logging()
# -

setup_notebook_logging(logging.INFO)

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
        max_plugin_failures: int = 5,
    ):
        self._config = {}
        self._configured_plugins = []        
        self.plugin_path = plugin_path
        self.config_path = config_path
        self.main_schema_file = main_schema_file
        self.plugin_schema_file = plugin_schema_file
        self._main_schema = None
        self._plugin_schema = None
        self.max_plugin_failures = max_plugin_failures
        self.plugin_failures = {}
        self.foreground_plugin = None

        # Initialize config if provided
        if config:
            self.config = config

        logger.debug("PluginManager initialized with default values.")

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, value):
        if not isinstance(value, dict):
            raise TypeError("Config must be a dictionary.")
        
        schema = self.main_schema
        if schema:
            logger.info("Validating config against main schema...")
            self._validate_config(value, schema)

        self._config = value
        logger.info("Configuration successfully updated.")

    @property
    def config_path(self):
        return self._config_path

    @config_path.setter
    def config_path(self, value):
        if not value:
            logger.warning("Config path set to None. Schema loading disabled.")
            self._config_path = None
            return

        if not isinstance(value, Path):
            value = Path(value)

        if not value.is_dir():
            raise FileNotFoundError(f"Config directory not found at {value}")

        self._config_path = value
        self._main_schema = None
        self._plugin_schema = None
        logger.info(f"Config path set to {self._config_path}")

    @property
    def plugin_path(self):
        return self._plugin_path

    @plugin_path.setter
    def plugin_path(self, value):
        if not value:
            logger.warning("Plugin path set to None.")
            self._config_path = None
            return

        if not isinstance(value, Path):
            value = Path(value)

        if not value.is_dir():
            raise FileNotFoundError(f"Plugin directory not found at {value}")

        self._plugin_path = value
        logger.info(f"Plugin path set to {self._plugin_path}")
    
    @property
    def main_schema(self):
        if self._main_schema is None:
            if not self._config_path or not self.main_schema_file:
                logger.warning("Config path or main schema file not set.")
                return {}

            schema_file = self._config_path / self.main_schema_file
            if not schema_file.is_file():
                raise FileNotFoundError(f"Main schema file not found at {schema_file}")

            logger.info(f"Loading main config schema from {schema_file}")
            with open(schema_file, "r") as f:
                self._main_schema = yaml.safe_load(f)
        return self._main_schema

    @property
    def plugin_schema(self):
        if self._plugin_schema is None:
            if not self._config_path or not self.plugin_schema_file:
                logger.warning("Config path or plugin schema file not set.")
                return {}

            schema_file = self._config_path / self.plugin_schema_file
            if not schema_file.is_file():
                raise FileNotFoundError(f"Plugin schema file not found at {schema_file}")

            logger.info(f"Loading plugin schema from {schema_file}")
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
            plugin_name = plugin_entry['plugin']
            base_config = plugin_entry['base_config']
    
            # 1. Validate Against Global Plugin Schema (Mandatory)
            global_schema = self.plugin_schema.get('plugin_config', {})
            logger.info("=" * 40)
            logger.info(f"Validating {plugin_name} against global schema...")
            self._validate_config(base_config, global_schema)

            # Assign UUID and final setup
            plugin_uuid = str(uuid.uuid4())[:8]
            base_config['uuid'] = plugin_uuid
            logger.info(f"Assigned UUID {plugin_uuid} to plugin {plugin_name}.")
    
            if not base_config.get('name'):
                base_config['name'] = f"{plugin_name}-{plugin_uuid}"
                logger.info(f"Set default plugin name to {base_config['name']}.")
    
        self._configured_plugins = value
        logger.info("All plugins validated and configured.")
        
        self._configured_plugins = value
        logger.info("configured_plugins successfully validated and set.")
    
    def reload_schemas(self):
        """
        Force reload of main and plugin schemas.
        """
        self._main_schema = None
        self._plugin_schema = None
        logger.info("Schemas reloaded.")

    def _load_plugin_schema(self, plugin_name):
        """
        Load the plugin-specific schema if it exists.
        """
        plugin_dir = self.plugin_path / plugin_name
        schema_file = plugin_dir / self.plugin_schema_file  # e.g., plugin_schema.yaml
    
        if schema_file.exists():
            logger.info(f"Loading plugin-specific schema for {plugin_name} from {schema_file}...")
            with open(schema_file, "r") as f:
                return yaml.safe_load(f)
        else:
            logger.info(f"No plugin-specific schema found for {plugin_name}. Skipping additional validation.")
            return {}
    
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

        logger.info("Config passed schema validation.")

    def load_plugins(self):
        """
        Locate and load plugins based on the configured_plugins property.
        Only load plugins that pass global and plugin-specific schema validation.
        """
        self.active_plugins = []
        self.dormant_plugins = []
        
        for entry in self.configured_plugins:
            plugin_name = entry['plugin']
            base_config = entry['base_config']
            plugin_params = entry.get('plugin_params', {})  # Defaults to empty if missing
        
            try:
                # 1. Validate Against Plugin-Specific Schema
                plugin_specific_schema = self._load_plugin_schema(plugin_name)
                if plugin_specific_schema:
                    logger.info(f"Validating {plugin_name} against its specific schema...")
                    self._validate_config(plugin_params, plugin_specific_schema)
    
                # 2. Import the plugin module dynamically
                module = import_module(f'plugins.{plugin_name}')
        
                # 3. Attach the update function from the module
                if hasattr(module.plugin, 'update_function'):
                    base_config['update_function'] = module.plugin.update_function
                else:
                    logger.warning(f"{plugin_name}: update_function not found. Skipping plugin.")
                    continue
        
                # 4. Load layout (if specified)
                if 'layout' in base_config:
                    layout_name = base_config['layout']
                    if hasattr(module.layout, layout_name):
                        layout = getattr(module.layout, layout_name)
                        base_config['layout'] = layout
                    else:
                        raise AttributeError(f"Layout '{layout_name}' not found in {plugin_name}")
                else:
                    logger.warning(f"{plugin_name} is missing a configured layout. Skipping plugin.")
                    continue
        
                # 5. Instantiate BasePlugin and pass configurations
                plugin_instance = BasePlugin(
                    **base_config,
                    cache_root=config['cache_root'],
                    cache_expire=config['cache_expire'],
                    resolution=config['resolution'],
                    config=plugin_params,  # Pass plugin_params as config
                )
                plugin_instance.update_function = base_config['update_function']
        
                # 6. Sort into active or dormant lists
                if base_config.get('dormant', False):
                    self.dormant_plugins.append(plugin_instance)
                    logger.info(f"Loaded dormant plugin: {plugin_name}")
                else:
                    self.active_plugins.append(plugin_instance)
                    logger.info(f"Loaded active plugin: {plugin_name}")
            except ValueError as e:
                logger.warning(f"{plugin_name}: Plugin-specific schema validation failed: {e}")
            except ModuleNotFoundError as e:
                logger.warning(f"{plugin_name} failed to load due to error: {e}. Skipping plugin.")
                continue
            except Exception as e:
                logger.error(f"Unexpected error loading {plugin_name}: {e}")
                continue
        
        logger.info(f"Loaded {len(self.active_plugins)} active plugins and {len(self.dormant_plugins)} dormant plugins.")
        
    def update_plugins(self):
        """
        Update all active plugins and check dormant plugins for activation.
        The foreground_plugin displays until its timer expires or a dormant plugin 
        activates as high-priority and interrupts the display.
        """
        if not self.foreground_plugin:
            self.foreground_plugin = self.active_plugins[0]
        # Update the foreground plugin if it's time
        if self.foreground_plugin and self.foreground_plugin.ready_for_update:
            logger.info(f"Updating foreground plugin: {self.foreground_plugin.name}")
            try:
                success = self.foreground_plugin.update()
                if not success:
                    self._handle_plugin_failure(self.foreground_plugin)
            except Exception as e:
                logger.error(f"Error updating {self.foreground_plugin.name}: {e}")
                self._handle_plugin_failure(self.foreground_plugin)
    
        # Always check dormant plugins for activation
        for plugin in self.dormant_plugins:
            if plugin.ready_for_update:
                logger.info(f"Checking dormant plugin: {plugin.name}")
                try:
                    success = plugin.update()
                    if success and plugin.high_priority:
                        logger.info(f"{plugin.name} activated as high-priority.")
                        self.foreground_plugin = plugin
                        break
                except Exception as e:
                    logger.error(f"Error updating dormant plugin {plugin.name}: {e}")
                    self._handle_plugin_failure(plugin)
    
        # Cycle to the next plugin if the foreground_plugin timer has expired
        if self.foreground_plugin and self.foreground_plugin.time_to_refresh <= 0:
            logger.info(f"{self.foreground_plugin.name} cycle complete. Moving to next plugin.")
            self._cycle_to_next_plugin()
    
    def _cycle_to_next_plugin(self):
        """Cycle to the next active plugin by UUID."""
        if not self.active_plugins:
            logger.warning("No active plugins to cycle.")
            self.foreground_plugin = None
            return
        
        if not self.foreground_plugin:
            # Start with the first active plugin if none is set
            self.foreground_plugin = self.active_plugins[0]
            logger.info(f"Foreground plugin set to: {self.foreground_plugin.name}")
            return
        
        # Locate current foreground plugin by UUID
        current_uuid = self.foreground_plugin.uuid
        current_index = next(
            (i for i, plugin in enumerate(self.active_plugins) if plugin.uuid == current_uuid),
            -1
        )
        
        if current_index == -1:
            logger.warning("Foreground plugin not found in active list. Resetting to first plugin.")
            self.foreground_plugin = self.active_plugins[0]
        else:
            # Cycle to the next plugin (loop back if at the end)
            next_index = (current_index + 1) % len(self.active_plugins)
            self.foreground_plugin = self.active_plugins[next_index]
            logger.info(f"Cycled to next plugin: {self.foreground_plugin.name}")

    def _handle_plugin_failure(self, plugin):
        uuid = plugin.uuid
        self.plugin_failures[uuid] = self.plugin_failures.get(uuid, 0) + 1
        
        if self.plugin_failures[uuid] >= self.max_plugin_failures:
            logger.warning(f"{plugin.name} removed after {self.max_plugin_failures} consecutive failures.")
            self.active_plugins.remove(plugin)
        else:
            logger.warning(f"{plugin.name} failed ({self.plugin_failures[uuid]}/{self.max_plugin_failures}).")

    def remove_plugin_by_uuid(self, plugin_uuid):
        """
        Remove a plugin from active or dormant lists based on UUID.
        """
        for plugin_list in [self.active_plugins, self.dormant_plugins]:
            for plugin in plugin_list:
                if plugin.uuid == plugin_uuid:
                    plugin_list.remove(plugin)
                    logger.info(f"Removed plugin {plugin.name} (UUID: {plugin_uuid})")
                    return True
        
        logger.warning(f"Plugin with UUID {plugin_uuid} not found.")
        return False


# -


# ! ln -s ../plugins ./

# +
m = PluginManager()

m.plugin_path = './plugins/'
m.config_path = '../config/'
m.main_schema_file = 'plugin_manager_schema.yaml'
m.plugin_schema_file = 'plugin_schema.yaml'

config = {
    'screen_mode': 'L',
    'resolution': (160, 190),
}

configured_plugins = [
    {'plugin': 'basic_clock',
         'base_config': {
            'name': 'Basic Clock',
            'duration': 100,
            # 'refresh_interval': 60,
            # 'dormant': False,
            'layout': 'layout',
         }
    },
    {'plugin': 'debugging',
        'base_config': {
            'name': 'Debugging 50',
            'dormant': True,
            'layout': 'layout',
            'refresh_interval': 2,
        },
        'plugin_params': {
            'title': 'Debugging 50',
            'crash_rate': 0.5,
            'high_priority_rate': 0.3,
            
        }
    }
    # {'plugin': 'word_clock',
    #     'base_config':{
    #         'name': 'Word Clock',
    #         'duration': 130,
    #         'refresh_interval': 60,
    #         'layout': 'layout',
    #     },
    #     'plugin_params': {
    #         'foo': 'bar',
    #         'spam': 7,
    #         'username': 'Monty'}
    # },
    # {'plugin': 'xkcd_comic',
    #     'base_config': {
    #         'name': 'XKCD',
    #         'duration': 200,
    #         'refresh_interval': 1800,
    #         'dormant': False,
    #         'layout': 'layout'
    #     },
    #     'plugin_params':{
    #         'max_x': 800,
    #         'max_y': 600,
    #         'resize': False,
    #         'max_retries': 5
    #     }
             
    # }
]
m.config = config
m.configured_plugins = configured_plugins
m.load_plugins()

# +
import time

# Toy loop to simulate plugin updates
logger.info("Starting toy loop to simulate plugin updates...")

loop_count = 0
max_loops = 20  # Stop after 20 loops for testing

while loop_count < max_loops:
    logger.info(f"\n--- Loop {loop_count + 1} ---")
    
    m.update_plugins()

    # Show currently active plugin and its data
    if m.foreground_plugin:
        plugin_name = m.foreground_plugin.name
        plugin_data = m.foreground_plugin.data
        logger.info(f"Foreground Plugin: {plugin_name}")
        logger.info(f"Plugin Data: {plugin_data}")
    else:
        logger.info("No active plugin at this time.")

    # Simulate a short delay to mimic update intervals
    time.sleep(1)
    
    loop_count += 1

logger.info("Toy loop completed.")
# -

m.active_plugins

from IPython.display import display

# +
m.update_plugins()

for i in m.dormant_plugins:
    if i.high_priority:
        display(i.image)
# -

m.dormant_plugins

i.high_priority

i.refresh_interval

i.image

i.update()

m.active_plugins[2].name
dir(m.active_plugins[2])

#

