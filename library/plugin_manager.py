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
import logging
import yaml
from typing import Optional, Dict, List
from uuid import uuid4
import json
import hashlib


# -

logger = logging.getLogger(__name__)


def validate_path(func):
    """
    Decorator to validate that the path is either a Path-like or None.
    Converts str -> Path if needed.
    Raises TypeError if invalid.
    """
    def wrapper(self, value):
        path_name = func.__name__
        logger.debug(f"Validating {path_name}: {value} ({type(value)})")        
        if value is None:
            # Path can remain None (valid usage).
            return func(self, value)
        if isinstance(value, str):
            # Convert string to a Path
            value = Path(value)
        if not isinstance(value, Path):
            # If it's neither None nor Path, raise
            raise TypeError(
                f"{func.__name__} must be a Path object, string, or None. "
                f"Got '{type(value).__name__}'."
            )
        return func(self, value)
    return wrapper


class PluginManager:
    """
    Manages loading, configuration, and lifecycle of plugins.
    
    This class can optionally validate its own `config` against a base schema,
    stored in a YAML file, if `base_schema_file` is provided. It also supports
    caching schema files to avoid repeated disk reads.
    """
    ACTIVE = 'active'
    DORMANT = 'dormant'
    LOAD_FAILED = 'load_failed'
    CONFIG_FAILED = 'config_failed',
    CRASHED = 'crashed'
    PENDING = 'pending_validation'   
    
    def __init__(
        self,
        plugin_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        config: Optional[dict] = None,
        base_schema_file: Optional[str] = None,
        plugin_schema_file: Optional[str] = None,
        plugin_param_filename: Optional[str] = 'plugin_param_schema.yaml',
        max_plugin_failures: int = 5,
    ):
        """
        Initialize the PluginManager with optional config, paths, and a base schema.

        Args:
            config (dict, optional): Base configuration for the manager. If None, an empty dict is used.
            plugin_path (Path or None): Directory containing plugin subdirectories.
            config_path (Path or None): Directory containing YAML schema files (and possibly other configs).
            base_schema_file (str or None): Filename of the base schema for validating `self.config`.
            max_plugin_failures (int): Consecutive plugin failures allowed before disabling a plugin.
        """
        # Use property setters for path validations
        self.plugin_path = plugin_path
        self.config_path = config_path
        
        # Internal cache for previously loaded schemas
        self._schema_cache: Dict[str, dict] = {}
        
        # Prepare data structures
        self.configured_plugins: List[dict] = []
        self.active_plugins: List[dict] = []
        self.dormant_plugins: List[dict] = []        

        # keys to be dropped when comparing plugin configs
        self._transient_config_keys = ['uuid', 'plugin_status']
        
        # Store schema filename (may be None if no base schema is used)
        self.base_schema_file = base_schema_file
        self.plugin_schema_file = plugin_schema_file
        self.plugin_param_filename = plugin_param_filename

        # maximum number of times a plugin can fail before being deactivated
        self.max_plugin_failures = max_plugin_failures

        # If no config given, store an empty dict and defer validation.
        if config is None:
            logger.debug("No initial config provided. Using empty dictionary.")
            self._config = {}
        else:
            # Triggers the config.setter
            self.config = config.copy()

        logger.info("PluginManager initialized.")
        
    # ----------------------------------------------------------------------
    #                        SCHEMA LOADING
    # ----------------------------------------------------------------------
    def load_schema(self, schema_file: str, cache: bool = True) -> dict:
        """
        Load and optionally cache a YAML schema file from `config_path` or from disk.
    
        Args:
            schema_file (str): The filename (or path) to the schema YAML.
            cache (bool): Whether to check and store the schema in the cache. Defaults to True.
    
        Returns:
            dict: Parsed schema data.
    
        Raises:
            FileNotFoundError: If the file is not found.
            ValueError: If the file is not valid YAML or is not a dict.
        """
        # Ensure schema_file is a Path object
        schema_path = Path(schema_file).resolve()
    
        # If caching is enabled, check for cached copy
        if cache and schema_path in self._schema_cache:
            logger.debug(f"Using cached schema for '{schema_path}'.")
            return self._schema_cache[schema_path]
    
        # Ensure the schema file exists
        if not schema_path.is_file():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
        # Load and parse the YAML
        try:
            with open(schema_path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML for '{schema_path}': {e}")
    
        if not isinstance(data, dict):
            raise ValueError(f"Schema '{schema_path}' is not a valid dictionary.")
    
        # Cache the schema only if caching is enabled
        if cache:
            self._schema_cache[schema_path] = data
            logger.info(f"Schema '{schema_path}' cached successfully.")
    
        logger.info(f"Schema '{schema_path}' loaded successfully.")
        return data
        
    def validate_config(self, config: dict, schema: dict) -> dict:
        """
        Validate `config` against a dict-based schema, returning a new dict 
        that merges defaults and logs warnings for errors.

        Args:
            config (dict): The configuration to be validated.
            schema (dict): Schema describing expected keys, types, and allowed values.

        Returns:
            dict: A *merged* config with defaults applied.

        Raises:
            ValueError: If validation fails for any required or type mismatch.
        """
        validated_config = {}
        errors = []

        for key, rules in schema.items():
            # Gather helpful info from the schema
            default_val = rules.get('default')
            required = rules.get('required', False)
            allowed = rules.get('allowed')
            # Convert string type to actual Python type
            try:
                expected_type = eval(rules.get('type', 'str'))
            except NameError:
                logger.warning(f"Unknown type in schema for '{key}'. Using 'str'.")
                expected_type = str

            if key not in config:
                # Missing key in user's config
                if required:
                    errors.append(
                        f"{key} is required but missing. Default: {default_val}"
                    )
                validated_config[key] = default_val
                continue

            # Key is present
            value = config[key]
            if not isinstance(value, expected_type):
                errors.append(
                    f"{key} must be of type {expected_type}, got {type(value).__name__}."
                )
                validated_config[key] = default_val
                continue

            # Check allowed values
            if allowed and value not in allowed:
                errors.append(
                    f"{key} must be one of {allowed}, got {value}."
                )
                validated_config[key] = default_val
                continue

            # If everything is good, store it
            validated_config[key] = value

        # Possibly allow extra keys that aren't in the schema, just log them
        for extra_key in config.keys() - schema.keys():
            logger.debug(f"Extra key '{extra_key}' in config not in schema. Keeping as-is.")
            validated_config[extra_key] = config[extra_key]

        # If any errors occurred, raise collectively
        if errors:
            for e in errors:
                logger.warning(e)
            raise ValueError("Configuration validation failed. Check logs for details.")

        logger.info("Configuration validated successfully.")
        return validated_config

    # ----------------------------------------------------------------------
    #                        CONFIG PROPERTIES
    # ----------------------------------------------------------------------
    @property
    def config(self) -> dict:
        """
        Access the manager's config dictionary (already validated if base_schema_file was provided).
        """
        return self._config

    @config.setter
    def config(self, value: dict):
        """
        Set (and possibly validate) the manager's base config.

        If `base_schema_file` is defined, load and validate. Otherwise, store as-is.
        """
        if not isinstance(value, dict):
            raise TypeError("Config must be a dictionary.")

        if self.base_schema_file:
            try:
                schema = self.load_schema(self.base_schema_file)
                merged = self.validate_config(value, schema)
                self._config = merged
                logger.info("Manager config validated and applied.")
            except Exception as e:
                logger.error(f"Manager config validation failed: {e}")
                raise
        else:
            # No schema? Just store
            self._config = value
            logger.debug("No base schema. Using config as-is.")
    
    # ----------------------------------------------------------------------
    # PATHS and FILES
    # ----------------------------------------------------------------------
    @property
    def plugin_path(self) -> Optional[Path]:
        """
        Directory containing plugin subdirectories.

        Returns:
            Path or None
        """
        return getattr(self, "_plugin_path", None)

    @plugin_path.setter
    @validate_path
    def plugin_path(self, value):
        self._plugin_path = value
        logger.debug(f"plugin_path set to {value}")

    @property
    def config_path(self) -> Optional[Path]:
        """
        Directory containing the YAML schema files and other configurations.

        Returns:
            Path or None
        """
        return getattr(self, "_config_path", None)

    @config_path.setter
    @validate_path
    def config_path(self, value):
        self._config_path = value
        logger.debug(f"config_path set to {value}")

    @property
    def base_schema_file(self):
        return self._base_schema_file

    @base_schema_file.setter
    def base_schema_file(self, value):
        self._base_schema_file = value

        if not value or not self.config_path:
            return

        schema_path = Path(self.config_path) / value
        if not schema_path.is_file():
            raise FileNotFoundError(f"Base schema file '{value}' does not exist at {schema_path}")

        self._base_schema_file = schema_path

    @property
    def plugin_schema_file(self):
        return self._plugin_schema_file
    
    @plugin_schema_file.setter
    def plugin_schema_file(self, value):
        # Store the raw value initially
        self._plugin_schema_file = value
        
        # If no value or config_path is None, skip the path check
        if not value or not self.config_path:
            return
        
        schema_path = Path(self.config_path) / value
    
        # --- Check cache before file existence ---
        if value in self._schema_cache or schema_path in self._schema_cache:
            logger.debug(f"Using cached schema for '{schema_path}'. Skipping file check.")
            self._plugin_schema_file = schema_path
            return
        
        # Perform file existence check only if not cached
        if not schema_path.is_file():
            raise FileNotFoundError(f"Plugin schema file '{value}' does not exist at {schema_path}")
    
        # Store the fully resolved path
        self._plugin_schema_file = schema_path

    # ----------------------------------------------------------------------
    #               PLUGIN LISTS AND THEIR SETTERS
    # ----------------------------------------------------------------------
    @property
    def configured_plugins(self) -> List[dict]:
        """
        A list of plugin configurations that have been set. Each entry is expected
        to contain at least:
        
            {
                'plugin': <plugin_name_str>,
                'plugin_config': {...}
                ...
            }

        Returns:
            list of dicts: The user-defined plugin config structures.
        """
        return self._configured_plugins

    @configured_plugins.setter
    def configured_plugins(self, plugins: List[dict]):
        """
        Set or replace the entire list of plugin configuration entries.
        Performs minimal validation that each entry is a dict with
        'plugin' and 'base_config'.

        Raises:
            TypeError: If `plugins` is not a list of dicts.
            ValueError: If any plugin dict is missing required keys.
        """
        if not plugins:
            logger.debug("No plugin configurations provided. Clearing list.")
            self._configured_plugins = []
            return

        if not isinstance(plugins, list):
            logger.error("configured_plugins must be a list.")
            raise TypeError("configured_plugins must be a list of dictionaries.")

        for plugin_dict in plugins:
            if not isinstance(plugin_dict, dict):
                logger.error("Invalid plugin format. Must be a dictionary.")
                raise TypeError("Each plugin must be a dictionary.")

            if 'plugin' not in plugin_dict or 'base_config' not in plugin_dict:
                logger.error("Missing 'plugin' or 'base_config' in plugin dict.")
                raise ValueError("Each plugin must have 'plugin' and 'base_config' keys.")

        logger.debug(f"Storing {len(plugins)} plugin configuration(s).")
        self._configured_plugins = plugins        

    def add_plugin(self, plugin_config: dict, force_duplicate: bool = False):
        """
        Add a plugin configuration to the list of configured plugins.
        
        Args:
            plugin_config (dict): The plugin configuration to validate and add.
        
        Raises:
            ValueError: If the plugin configuration does not conform to the schema.
            FileNotFoundError: If the plugin schema file is missing.
        """
        if not self.plugin_schema_file:
            raise FileNotFoundError("Plugin schema is required, but is not set.")
    
        plugin_id = plugin_config.get('plugin')
        if not plugin_id:
            raise ValueError("Plugin configuration does not contain a valid 'plugin' identifier.")
    
        # Prepare initial status
        plugin_status = {
            'status': self.PENDING,
            'reason': 'Pending validation'
        }
    
        # Load base plugin schema
        plugin_schema_file_path = self.plugin_schema_file
        try:
            plugin_schema = self.load_schema(plugin_schema_file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"Base plugin schema file not found at {plugin_schema_file_path}")
        
        # Validate plugin config
        try:
            validated_plugin_config = self.validate_config(
                plugin_config.get('plugin_config', {}),
                plugin_schema
            )
        except ValueError:
            plugin_status['status'] = self.CONFIG_FAILED
            plugin_status['reason'] = 'Plugin config validation failed'
            logger.error(f"Plugin config validation failed for {plugin_id}")
            raise
    
        # Attempt to load per-plugin param schema (optional)
        try:
            plugin_param_schema_file = self.plugin_path / plugin_id / self.plugin_param_filename
            plugin_param_schema = self.load_schema(plugin_param_schema_file, cache=False)
        except FileNotFoundError:
            logger.debug(f"Parameters schema file not found for plugin '{plugin_id}'. Assuming none required.")
            plugin_param_schema = {}
    
        # Validate plugin parameters if available
        plugin_params = plugin_config.get('plugin_params', {})
        try:
            if plugin_params and not plugin_param_schema:
                logger.warning(
                    f"Supplied parameters for plugin '{plugin_id}' cannot be validated "
                    "due to missing param schema file."
                )
            validated_plugin_params = self.validate_config(plugin_params, plugin_param_schema)
        except ValueError:
            plugin_status['status'] = self.CONFIG_FAILED
            plugin_status['reason'] = 'Plugin params validation failed'
            logger.error(f"Plugin params validation failed for {plugin_id}")
            raise
    
        # Determine final plugin status
        if validated_plugin_config.get('dormant', False):
            plugin_status.update(status=self.DORMANT, reason='Configuration validated (dormant)')
        else:
            plugin_status.update(status=self.ACTIVE, reason='Configuration validated')
    
        # Generate partial-UUID for tracking
        plugin_uuid = str(uuid4())[:8]
    
        # Build final config
        final_config = {
            'plugin': plugin_id,
            'plugin_config': validated_plugin_config,
            'plugin_params': validated_plugin_params,
            'uuid': plugin_uuid,
            'plugin_status': plugin_status
        }
    
        # Check for duplicate configurations
    
        if not force_duplicate:
            new_signature = self.plugin_config_signature(final_config)
            for existing_plugin in self.configured_plugins:
                if self.plugin_config_signature(existing_plugin) == new_signature:
                    existing_uuid = existing_plugin.get('uuid')
                    existing_name = existing_plugin.get('plugin_config', {}).get('name', 'UNSET NAME')
                    logger.info(f"Plugin is identical to {existing_name}, UUID: {existing_uuid}. Skipping addition. Use `force_duplicate=True` to force.")
                    return
                    
        # Add to configured plugins
        self.configured_plugins.append(final_config)
    
        # Log success
        logger.info(
            f"Plugin '{plugin_id}' added with UUID={plugin_uuid} and status={plugin_status['status']}."
        )
        return final_config

    def plugin_config_signature(self, plugin_config: dict) -> str:
        """Generate a hash signature of a plugin config, ignoring transient fields."""
        cfg = dict(plugin_config)
        
        # Remove transient fields like 'uuid' from comparison
        for key in self._transient_config_keys:
            cfg.pop(key, None)

        # Convert to deterministic JSON and hash it
        cfg_json = json.dumps(cfg, sort_keys=True)
        return hashlib.md5(cfg_json.encode('utf-8')).hexdigest()  

    # # ----- VALIDATION -----
    # def load_schema(self, schema_file: str) -> dict:
    #     """
    #     Load and cache schema files for reuse.

    #     Args:
    #         schema_file (str): The schema file to load.

    #     Returns:
    #         dict: Parsed schema dictionary.

    #     Raises:
    #         FileNotFoundError: If the schema file does not exist.
    #         ValueError: If the schema cannot be parsed.
    #     """
    #     # Check cache first
    #     if schema_file in self._schema_cache:
    #         logger.debug(f"Schema '{schema_file}' loaded from cache.")
    #         return self._schema_cache[schema_file]

    #     # Construct schema path
    #     schema_path = self.config_path / schema_file if self.config_path else Path(schema_file)

    #     if not schema_path.is_file():
    #         raise FileNotFoundError(f"Schema file not found: {schema_path}")

    #     try:
    #         with open(schema_path, 'r') as file:
    #             schema = yaml.safe_load(file)
    #             self._schema_cache[schema_file] = schema  # Cache schema
    #             logger.info(f"Schema '{schema_file}' loaded successfully.")
    #             return schema
    #     except Exception as e:
    #         raise ValueError(f"Failed to load schema '{schema_file}': {e}")

    # def validate_config(self, config: dict, schema: dict) -> dict:
    #     """
    #     Validate a configuration dictionary against a schema.

    #     Args:
    #         config (dict): The configuration to validate.
    #         schema (dict): The schema to validate against.

    #     Returns:
    #         dict: Validated configuration with defaults applied.
    #     """
    #     validated_config = {}
    #     errors = []

    #     for key, rules in schema.items():
    #         if key not in config:
    #             if rules.get('required', False):
    #                 errors.append(f"{key} is required but missing. Default: {rules.get('default')}")
    #             validated_config[key] = rules.get('default')
    #         else:
    #             value = config[key]
    #             expected_type = eval(rules['type'])
                
    #             if not isinstance(value, expected_type):
    #                 errors.append(f"{key} must be of type {expected_type}, got {type(value).__name__}. Default: {rules.get('default')}")
    #                 validated_config[key] = rules.get('default')
    #             else:
    #                 validated_config[key] = value

    #             if 'allowed' in rules and value not in rules['allowed']:
    #                 errors.append(f"{key} must be one of {rules['allowed']}, got {value}. Default: {rules.get('default')}")
    #                 validated_config[key] = rules.get('default')

    #     if errors:
    #         for error in errors:
    #             logger.warning(error)
    #         raise ValueError("Configuration validation failed. Check logs for details.")
        
    #     logger.info("Configuration validated successfully.")
    #     return validated_config



# +
# def validate_path(func):
#     """
#     Decorator to validate and convert path-like properties.
    
#     This decorator ensures that a given path is either:
#       - A `Path` object
#       - A `str` that can be converted to a `Path` object
#       - `None` (allowed for unset paths)
    
#     If the path is invalid (e.g., an integer or unsupported type), a `TypeError` is raised.
    
#     Additionally, the decorator logs the validation process, including:
#       - Conversion of strings to `Path` objects
#       - Error messages for invalid types
#       - Successful validation of paths
    
#     Args:
#         func (function): The setter method for the path property to be validated.
    
#     Returns:
#         function: A wrapped function that validates and sets the path.
    
#     Raises:
#         TypeError: If the provided path is not a `Path`, `str`, or `None`.
    
#     Example:
#         @property
#         def plugin_path(self):
#             return self._plugin_path
    
#         @plugin_path.setter
#         @validate_path
#         def plugin_path(self, path):
#             self._plugin_path = path
#     """    
#     def wrapper(self, path):
#         path_name = func.__name__
#         logger.debug(f"Validating {path_name}: {path} ({type(path)})")
        
#         if path is None:
#             logger.debug(f"{path_name} set to None")
#             return func(self, None)
        
#         if isinstance(path, str):
#             logger.debug(f"Converting {path_name} to Path.")
#             path = Path(path)

#         if isinstance(path, Path):
#             logger.debug(f"{path_name} is valid: {path}")
#             return func(self, path)
        
#         message = f"Invalid type for {path_name}. Must be Path, str, or None."
#         logger.error(message)
#         raise TypeError(message)
    
#     return wrapper

# +
# from pathlib import Path
# import yaml
# import logging
# import uuid
# from importlib import import_module


# try:
#     from .exceptions import PluginError, ImageError, PluginTimeoutError, FileError, ConfigurationError
#     from .base_plugin import BasePlugin
# except ImportError:
#     # support jupyter developement
#     from exceptions import PluginError, ImageError, PluginTimeoutError, FileError, ConfigurationError
#     from base_plugin import BasePlugin

# +
# logger = logging.getLogger(__name__)

# +
# import sys
# # Configure logging to show in Jupyter Notebook with detailed output
# def setup_notebook_logging(level=logging.DEBUG):
#     log_format = (
#         '%(asctime)s [%(levelname)s] [%(name)s] '
#         '[%(module)s.%(funcName)s] [%(lineno)d] - %(message)s'
#     )
    
#     # Clear any existing handlers to prevent duplicate logging
#     for handler in logging.root.handlers[:]:
#         logging.root.removeHandler(handler)

#     # Set up logging for notebook
#     logging.basicConfig(
#         level=level,
#         format=log_format,
#         handlers=[logging.StreamHandler(sys.stdout)]
#     )
    
#     logging.getLogger(__name__).debug("Notebook logging configured.")

# # Run this cell to enable logging
# setup_notebook_logging()

# +
# class PluginManager:
#     """
#     Manages the loading, configuration, and lifecycle of plugins.

#     This class handles plugin discovery, schema validation, dynamic loading,
#     and execution of plugins. It supports active and dormant plugins, with the
#     ability to update, remove, and reconfigure plugins at runtime.

#     Attributes:
#         plugin_path (Path): Path to the directory containing plugins.
#         config_path (Path): Path to the configuration directory.
#         max_plugin_failures (int): Maximum number of consecutive failures before a plugin is removed.
#         foreground_plugin (BasePlugin): The currently active plugin being displayed.
    
#     Example:
#         manager = PluginManager(config=config, plugin_path=Path('./plugins'))
#         manager.load_plugins()
#         manager.update_plugins()
#     """    
#     # ----- Plugin Status Constants
#     ACTIVE = 'active'
#     DORMANT = 'dormant'
#     LOAD_FAILED = 'load_failed'
#     PENDING = 'pending_validation'
    
#     # ----- Init
#     def __init__(
#         self,
#         config: dict = None,
#         plugin_path: Path = None,
#         config_path: Path = None,
#         main_schema_file: str = None,
#         plugin_schema_file: str = None,
#         max_plugin_failures: int = 5,
#     ):
#         """
#         Initialize the PluginManager.

#         Args:
#             config (dict, optional): Initial configuration for the plugin manager.
#             plugin_path (Path, optional): Path to the plugin directory.
#             config_path (Path, optional): Path to the configuration directory.
#             main_schema_file (str, optional): Main schema file for validating the config.
#             plugin_schema_file (str, optional): Schema file for validating individual plugins.
#             max_plugin_failures (int, optional): Number of allowed consecutive failures before a plugin is removed (default: 5).
#         """
#         self._config = {}
#         self._configured_plugins = []
#         self.active_plugins = []
#         self.dormant_plugins = []
#         self.plugin_path = plugin_path
#         self.config_path = config_path
#         self.main_schema_file = main_schema_file
#         self.plugin_schema_file = plugin_schema_file
#         self._main_schema = None
#         self._plugin_schema = None
#         self.max_plugin_failures = max_plugin_failures
#         self.plugin_failures = {}
#         self.foreground_plugin = None

#         # Initialize config if provided
#         if config:
#             self.config = config

#         logger.debug("PluginManager initialized with default values.")

#     # ----- Configuration and Schema
#     @property
#     def config(self):
#         """
#         Get or set the PluginManager configuration.

#         The configuration is validated against the main schema when updated.
        
#         Returns:
#             dict: The current configuration.

#         Raises:
#             TypeError: If the provided value is not a dictionary.
#             ValueError: If the value fails validation against the schema.
#         """
#         return self._config

#     @config.setter
#     def config(self, value):
#         if not isinstance(value, dict):
#             raise TypeError("Config must be a dictionary.")
        
#         schema = self.main_schema
#         if schema:
#             logger.info("Validating config against main schema...")
#             try:
#                 self._validate_config(value, schema)
#             except ValueError as e:
#                 logger.error(f"Failed to validate configuration: {e}")
#                 return

#         self._config = value
#         logger.info("Configuration successfully updated.")

#     @property
#     def config_path(self):
#         """
#         Get or set the configuration directory path.

#         When updated, the schemas are reloaded, and the path is validated to ensure
#         it exists and is a directory.

#         Returns:
#             Path or None: The current configuration directory path.

#         Raises:
#             FileNotFoundError: If the provided path does not exist or is not a directory.
#         """
#         return self._config_path

#     @config_path.setter
#     def config_path(self, value):
#         if not value:
#             logger.warning("Config path set to None. Schema loading disabled.")
#             self._config_path = None
#             return

#         if not isinstance(value, Path):
#             value = Path(value)

#         if not value.is_dir():
#             raise FileNotFoundError(f"Config directory not found at {value}")

#         self._config_path = value
#         self._main_schema = None
#         self._plugin_schema = None
#         logger.info(f"Config path set to {self._config_path}")

#     @property
#     def plugin_path(self):
#         """
#         Get or set the plugin directory path.

#         Ensures the path exists and points to a valid directory. If set to None,
#         a warning is logged and the plugin path is cleared.

#         Returns:
#             Path or None: The current plugin directory path.

#         Raises:
#             FileNotFoundError: If the provided path does not exist or is not a directory.
#         """
#         return self._plugin_path

#     @plugin_path.setter
#     def plugin_path(self, value):
#         if not value:
#             logger.warning("Plugin path set to None.")
#             self._config_path = None
#             return

#         if not isinstance(value, Path):
#             value = Path(value)

#         if not value.is_dir():
#             raise FileNotFoundError(f"Plugin directory not found at {value}")

#         self._plugin_path = value
#         logger.info(f"Plugin path set to {self._plugin_path}")
    
#     @property
#     def main_schema(self):
#         """
#         Load and return the main schema.

#         The schema is lazily loaded from a YAML file the first time it is accessed.
#         If the schema file or config path is not set, a warning is logged, and an empty
#         dictionary is returned. The schema is cached for future access.

#         Returns:
#             dict: The loaded main schema or an empty dictionary if not set.

#         Raises:
#             FileNotFoundError: If the main schema file is not found.
#         """
#         if self._main_schema is None:
#             if not self._config_path or not self.main_schema_file:
#                 logger.warning("Config path or main schema file not set.")
#                 return {}

#             schema_file = self._config_path / self.main_schema_file
#             if not schema_file.is_file():
#                 raise FileNotFoundError(f"Main schema file not found at {schema_file}")

#             logger.info(f"Loading main config schema from {schema_file}")
#             with open(schema_file, "r") as f:
#                 self._main_schema = yaml.safe_load(f)
#         return self._main_schema

#     @property
#     def plugin_schema(self):
#         """
#         Load and return the plugin schema.

#         The schema is lazily loaded from a YAML file when first accessed. If the
#         schema file or config path is not set, a warning is logged, and an empty
#         dictionary is returned. The schema is cached after the initial load.

#         Returns:
#             dict: The loaded plugin schema or an empty dictionary if not set.

#         Raises:
#             FileNotFoundError: If the plugin schema file is not found.
#         """
#         if self._plugin_schema is None:
#             if not self._config_path or not self.plugin_schema_file:
#                 logger.warning("Config path or plugin schema file not set.")
#                 return {}

#             schema_file = self._config_path / self.plugin_schema_file
#             if not schema_file.is_file():
#                 raise FileNotFoundError(f"Plugin schema file not found at {schema_file}")

#             logger.info(f"Loading plugin schema from {schema_file}")
#             with open(schema_file, "r") as f:
#                 self._plugin_schema = yaml.safe_load(f)
#         return self._plugin_schema

#     def reload_schemas(self):
#         """
#         Force reload of main and plugin schemas.

#         This method clears the cached schemas, forcing them to be reloaded
#         the next time they are accessed.
#         """
#         self._main_schema = None
#         self._plugin_schema = None
#         logger.info("Schemas reloaded.")

#     def reconfigure_plugin(self, plugin_uuid: str, new_config: dict, new_params: dict = None):
#         """
#         Reconfigure an existing plugin by UUID.
        
#         Args:
#             plugin_uuid (str): UUID of the plugin to reconfigure.
#             new_config (dict): Updated base configuration for the plugin.
#             new_params (dict, optional): Updated plugin-specific parameters.
    
#         Raises:
#             ValueError: If the plugin cannot be found or validation fails.
#         """
#         # Locate the plugin in active or dormant lists
#         plugin = next(
#             (p for p in self.active_plugins + self.dormant_plugins if p.uuid == plugin_uuid),
#             None
#         )
    
#         if not plugin:
#             raise ValueError(f"Plugin with UUID {plugin_uuid} not found.")
    
#         plugin_name = plugin.name
        
#         # Validate new base configuration against global plugin schema
#         logger.info(f"Reconfiguring plugin: {plugin_name} (UUID: {plugin_uuid})")
#         global_schema = self.plugin_schema.get('plugin_config', {})
#         try:
#             self._validate_config(new_config, global_schema)            
    
#             # Load and validate plugin-specific schema if params are provided
#             if new_params:
#                 plugin_schema = self._load_plugin_schema(plugin_name)
#                 if plugin_schema:
#                     logger.info(f"Validating {plugin_name} against specific schema...")
#                     self._validate_config(new_params, plugin_schema)
        
#                 # Update plugin-specific parameters
#                 plugin.config.update(new_params)
#         except ValueError as e:
#             logger.error(f"Failed to reconfigure plugin {plugin_name} (UUID: {plugin_uuid}): {e}")
#             return
    
#         # Apply new base configuration
#         plugin.duration = new_config.get('duration', plugin.duration)
#         plugin.refresh_interval = new_config.get('refresh_interval', plugin.refresh_interval)
#         plugin.dormant = new_config.get('dormant', plugin.dormant)
#         plugin.layout_data = new_config.get('layout', plugin.layout_data)
    
#         if 'name' in new_config:
#             plugin.name = new_config['name']
    
#         # Force refresh by resetting last_updated
#         plugin.last_updated = 0
#         logger.info(f"Plugin {plugin_name} reconfigured successfully.")

#     def _load_plugin_schema(self, plugin_name):
#         """
#         Load and return a plugin-specific schema if available.

#         This method attempts to load a schema YAML file from the plugin's directory.
#         If the schema file exists, it is read and returned as a dictionary. If not,
#         a log message is issued, and an empty dictionary is returned.

#         Args:
#             plugin_name (str): The name of the plugin whose schema should be loaded.

#         Returns:
#             dict: The loaded plugin schema or an empty dictionary if no schema file is found.
#         """
#         plugin_dir = self.plugin_path / plugin_name
#         schema_file = plugin_dir / self.plugin_schema_file  # e.g., plugin_schema.yaml
    
#         if schema_file.exists():
#             logger.info(f"Loading plugin-specific schema for {plugin_name} from {schema_file}...")
#             with open(schema_file, "r") as f:
#                 return yaml.safe_load(f)
#         else:
#             logger.info(f"No plugin-specific schema found for {plugin_name}. Skipping additional validation.")
#             return {}
    
#     def _validate_config(self, config, schema):
#         """
#         Validate configuration against a schema.
        
#         Args:
#             config (dict): Configuration to validate.
#             schema (dict): Schema to validate against.

#         Raises:
#             ValueError: If the config does not match the schema.
#         """
#         errors = []
        
#         for key, params in schema.items():
#             description = params.get('description', 'No description available')
            
#             # Set default if key is missing and not required
#             if key not in config:
#                 if params.get('required', False):
#                     errors.append(f"{key} is required but missing. Description: {description}")
#                 else:
#                     config[key] = params.get('default')
#                 continue
            
#             # Extract the value and expected type
#             value = config[key]
#             expected_type = params['type']

#             # Handle multiple types (including NoneType)
#             if isinstance(expected_type, str) and ',' in expected_type:
#                 # Convert to tuple of types (str, int, float, NoneType)
#                 type_mappings = {
#                     'str': str,
#                     'int': int,
#                     'float': float,
#                     'bool': bool,
#                     'None': type(None),
#                     'dict': dict
#                 }
#                 expected_type = tuple(
#                     type_mappings[t.strip()] for t in expected_type[1:-1].split(',')
#                 )
#             else:
#                 expected_type = eval(expected_type if expected_type != 'None' else 'type(None)')
            
#             # Type check
#             if not isinstance(value, expected_type):
#                 errors.append(
#                     f"{key} must be of type {expected_type} (got {type(value).__name__}). "
#                     f"Description: {description}"
#                 )

#             # Allowed values check
#             allowed = params.get('allowed')
#             if allowed and value not in allowed:
#                 errors.append(
#                     f"{key} must be one of {allowed} (got {value}). "
#                     f"Description: {description}"
#                 )

#         # Raise if errors occurred
#         if errors:
#             raise ValueError("Config validation failed:\n" + "\n".join(errors))

#         logger.info("Config passed schema validation.")
    
#     # ----- Plugin Creation and Deletion
#     @property
#     def configured_plugins(self):
#         """
#         Get the list of configured plugins.

#         Returns:
#             list: A list of dictionaries representing plugin configurations.
#         """
#         return self._configured_plugins

#     @configured_plugins.setter
#     def configured_plugins(self, value):
#         """
#         Set and validate the list of configured plugins.

#         This setter method ensures that the provided value is a list of plugin configurations.
#         Each plugin configuration is validated against the global plugin schema. UUIDs are
#         assigned to each plugin during validation. If a plugin lacks a name, a default name
#         based on the plugin name and UUID is assigned.

#         Args:
#             value (list): A list of plugin configuration dictionaries, each containing 
#                           'plugin' and 'base_config' keys.

#         Raises:
#             TypeError: If the provided value is not a list.
#             ValueError: If plugin validation fails.
#         """
#         if not isinstance(value, list):
#             raise TypeError("configured_plugins must be a list of plugin configurations.")
    
#         for plugin_entry in value:
#             plugin_name = plugin_entry['plugin']
#             base_config = plugin_entry['base_config']
    
#             # 1. Validate Against Global Plugin Schema (Mandatory)
#             global_schema = self.plugin_schema.get('plugin_config', {})
#             logger.info("=" * 40)
#             logger.info(f"Validating {plugin_name} against global schema...")
#             try:
#                 self._validate_config(base_config, global_schema)
#             except ValueError as e:
#                 error_message = str(e)
#                 if 'layout_name is required but missing' in error_message:
#                     msg = f"{plugin_name} missing 'layout_name'. Marking as 'load_failed'."
#                     logger.warning(msg)
#                     plugin_entry['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': msg}
#                     continue  # Skip adding this plugin
            

#             # Assign UUID and final setup
#             plugin_uuid = str(uuid.uuid4())[:8]
#             base_config['uuid'] = plugin_uuid
#             logger.info(f"Assigned UUID {plugin_uuid} to plugin {plugin_name}.")
    
#             if not base_config.get('name'):
#                 base_config['name'] = f"{plugin_name}-{plugin_uuid}"
#                 logger.info(f"Set default plugin name to {base_config['name']}.")
    
#         self._configured_plugins = value
#         logger.info("All plugins validated and configured.")
        
#         self._configured_plugins = value
#         logger.info("configured_plugins successfully validated and set.")

#     def load_plugins(self):
#         """
#         Locate and load plugins based on the configured_plugins property.
#         Only load plugins that pass global and plugin-specific schema validation.
#         """

#         logger.info("Loading configured plugins...")
            
#         self.active_plugins = []
#         self.dormant_plugins = []
        
#         logger.info("Loading all configured plugins...")
        
#         all_plugins = self.active_plugins + self.dormant_plugins
#         loaded_uuids = [p.uuid for p in self.active_plugins + self.dormant_plugins]    
#         for plugin_config in self.configured_plugins:
#             plugin_uuid = plugin['base_config'].get('uuid')
#             if plugin_uuid in loaded_uuids:
#                 logger.info(f"Plugin {plugin['plugin']} (UUID: {plugin_uuid}) is already loaded. Skipping load.")
#                 continue
#             # plugin_uuid = plugin_config['base_config'].get('uuid')
    
#             # # Check if the plugin is already loaded
#             # existing_plugin = next(
#             #     (p for p in self.active_plugins + self.dormant_plugins if p.uuid == plugin_uuid),
#             #     None
#             # )
    
#             # if existing_plugin:
#             #     logger.info(f"Plugin {plugin_config['plugin']} (UUID: {plugin_uuid}) already loaded. Skipping.")
#             #     continue  # Skip the rest of the loading logic for this plugin
    
#             # Attempt to add the plugin
#             success = self.add_plugin(plugin_config)
#             if not success:
#                 logger.warning(f"Failed to load plugin: {plugin_config['plugin']}")
#             else:
#                 logger.info(f"Successfully loaded plugin: {plugin_config['plugin']}")
    
#         logger.info(f"Loaded {len(self.active_plugins)} active plugins and {len(self.dormant_plugins)} dormant plugins.")
        
#     def list_plugins(self):
#         """
#         List all configured plugins with their name, UUID, and status.
        
#         Returns:
#             dict: Dictionary containing lists of plugins categorized by status.
#         """
#         logger.info("\n--- Configured Plugins ---")
#         plugin_summary = {
#             'active': [],
#             'dormant': [],
#             'load_failed': [],
#             'unknown': []
#         }
    
#         for plugin_config in self.configured_plugins:
#             plugin_name = plugin_config['base_config'].get('name', 'Unnamed Plugin')
#             uuid = plugin_config['base_config'].get('uuid', 'No UUID')
#             status_info = plugin_config.get('plugin_status', {})
#             status = status_info.get('status', 'unknown')
#             reason = status_info.get('reason', 'No reason provided')
    
#             logger.info(f"Name: {plugin_name}, UUID: {uuid}, Status: {status}, Reason: {reason}")
            
#             # Categorize the plugin based on its status
#             if status in plugin_summary:
#                 plugin_summary[status].append({
#                     'name': plugin_name,
#                     'uuid': uuid,
#                     'status': status,
#                     'reason': reason
#                 })
#             else:
#                 plugin_summary['unknown'].append({
#                     'name': plugin_name,
#                     'uuid': uuid,
#                     'status': 'unknown',
#                     'reason': reason
#                 })
    
#         return plugin_summary

    
#     def remove_plugin(self, plugin_uuid):
#         """
#         Public method to fully remove a plugin by UUID.
        
#         This method removes the plugin from active and dormant lists,
#         and also deletes its configuration from the configured_plugins list.
        
#         Args:
#             plugin_uuid (str): UUID of the plugin to remove.
    
#         Returns:
#             bool: True if the plugin was successfully removed, False if the plugin was not found.
#         """
    
#         active_success = self._remove_plugin_by_uuid(plugin_uuid)
#         success = False
#         configured_uuids = [p['base_config'].get('uuid') for p in self.configured_plugins]

#         if plugin_uuid in configured_uuids:
#             self._configured_plugins = [
#                 p for p in self.configured_plugins if p['base_config'].get('uuid') != plugin_uuid
#             ]
#             logger.info(f"Removed plugin configuration with UUID: {plugin_uuid}")
#             success = True

#         if active_success:
#             logger.info(f"Removed active/dormant plugin with UUID: {plugin_uuid}")
#             success = True
#         else:
#             logger.info(f"Plugin UUID: {plugin_uuid} was not active or dormant.")    
    
#     def _remove_plugin_by_uuid(self, plugin_uuid):
#         """
#         Private method to remove a plugin from active or dormant lists by UUID.
        
#         Args:
#             plugin_uuid (str): UUID of the plugin to remove.
    
#         Returns:
#             bool: True if the plugin was removed, False if the plugin was not found.
#         """
#         for plugin_list in [self.active_plugins, self.dormant_plugins]:
#             for plugin in plugin_list:
#                 if plugin.uuid == plugin_uuid:
#                     plugin_list.remove(plugin)
#                     logger.info(f"Removed plugin {plugin.name} (UUID: {plugin_uuid})")
    
#                     # Handle foreground plugin cycling if the removed plugin was active
#                     if plugin == self.foreground_plugin:
#                         logger.info(f"{plugin.name} was the foreground plugin. Cycling to the next.")
#                         self._cycle_to_next_plugin()
    
#                     return True
        
#         logger.warning(f"Plugin with UUID {plugin_uuid} not found in active/dormant lists.")
#         return False
    
    
#     def _cycle_to_next_plugin(self):
#         """
#         Cycle to the next active plugin by UUID.
        
#         If no active plugins are available, the foreground plugin is set to None.
#         """
#         if not self.active_plugins:
#             logger.warning("No active plugins to cycle.")
#             self.foreground_plugin = None
#             return
        
#         # Cycle to the next active plugin
#         if self.foreground_plugin:
#             current_uuid = self.foreground_plugin.uuid
#             current_index = next(
#                 (i for i, plugin in enumerate(self.active_plugins) if plugin.uuid == current_uuid),
#                 -1
#             )
    
#             next_index = (current_index + 1) % len(self.active_plugins) if current_index != -1 else 0
#             self.foreground_plugin = self.active_plugins[next_index]
#             logger.info(f"Cycled to next plugin: {self.foreground_plugin.name}")
#         else:
#             # Default to the first active plugin if no foreground exists
#             self.foreground_plugin = self.active_plugins[0]
#             logger.info(f"Foreground plugin set to: {self.foreground_plugin.name}")

#     def add_plugin(self, plugin_config: dict):
#         """
#         Add a new plugin to the manager.
    
#         Args:
#             plugin_config (dict): Plugin configuration dictionary with 'plugin', 'base_config', and optional 'plugin_params'.
    
#         Returns:
#             bool: True if the plugin was added successfully, False if the plugin failed to load or validate.
#         """
#         required_keys = ['plugin', 'base_config']
#         add_config = True
#         for key in required_keys:
#             if key not in plugin_config:
#                 logger.error(f"Plugin configuration missing required key: {key}")
#                 plugin_config['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': f"Missing required key: {key}"}
#                 return False
    
#         plugin_name = plugin_config['plugin']
#         base_config = plugin_config['base_config']
#         plugin_params = plugin_config.get('plugin_params', {})
#         configured_plugin_uuids = [p['base_config'].get('uuid') for p in self.configured_plugins]
#         if base_config.get('uuid') in configured_plugin_uuids:
#             add_config = False

    
#         # Default to load_failed until plugin is successfully loaded
#         plugin_config['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': 'Pending validation'}
    
#         try:
#             # Validate Against Global Plugin Schema
#             global_schema = self.plugin_schema.get('plugin_config', {})
#             logger.info(f"Validating {plugin_name} against global schema...")
#             self._validate_config(base_config, global_schema)
    
#             # Validate Against Plugin-Specific Schema (if available)
#             plugin_specific_schema = self._load_plugin_schema(plugin_name)
#             if plugin_specific_schema:
#                 logger.info(f"Validating {plugin_name} against plugin-specific schema...")
#                 self._validate_config(plugin_params, plugin_specific_schema)
    
#             # Assign UUID if not already assigned
#             if 'uuid' not in base_config:
#                 plugin_uuid = str(uuid.uuid4())[:8]
#                 base_config['uuid'] = plugin_uuid
#                 logger.info(f"Assigned UUID {plugin_uuid} to new plugin {plugin_name}.")
    
#             if not base_config.get('name'):
#                 base_config['name'] = f"{plugin_name}-{base_config['uuid']}"
#                 logger.info(f"Set default plugin name to {base_config['name']}.")
    
#             # Load the Plugin
#             module = import_module(f'plugins.{plugin_name}')
    
#             if hasattr(module.plugin, 'update_function'):
#                 base_config['update_function'] = module.plugin.update_function
#             else:
#                 msg = f"{plugin_name}: update_function not found"
#                 logger.warning(msg)
#                 plugin_config['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': msg}
#                 return False
    
#             # Load layout
#             if 'layout_name' in base_config:
#                 layout_name = base_config['layout_name']
#                 if hasattr(module.layout, layout_name):
#                     layout = getattr(module.layout, layout_name)
#                     base_config['layout'] = layout
#                 else:
#                     msg = f"Layout '{layout_name}' not found in {plugin_name}"
#                     logger.warning(msg)
#                     plugin_config['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': msg}
#                     return False
#             else:
#                 msg = f"{plugin_name} is missing a configured layout_name"
#                 logger.warning(msg)
#                 plugin_config['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': msg}
#                 return False
    
#             # Instantiate and Add to Active/Dormant Lists
#             plugin_instance = BasePlugin(
#                 **base_config,
#                 cache_root=self.config['cache_root'],
#                 cache_expire=self.config['cache_expire'],
#                 resolution=self.config['resolution'],
#                 config=plugin_params,
#             )
#             plugin_instance.update_function = base_config['update_function']
    
#             # Determine plugin status and list
#             if base_config.get('dormant', False):
#                 self.dormant_plugins.append(plugin_instance)
#                 plugin_config['plugin_status'] = {'status': self.DORMANT, 'reason': 'Loaded successfully'}
#                 logger.info(f"Added dormant plugin: {plugin_name}")
#             else:
#                 self.active_plugins.append(plugin_instance)
#                 plugin_config['plugin_status'] = {'status': self.ACTIVE, 'reason': 'Loaded successfully'}
#                 logger.info(f"Added active plugin: {plugin_name}")
    
#             # Add to configured plugins list only if new
#             if add_config:
#                 self._configured_plugins.append(plugin_config)
    
#             return True
    
#         except ValueError as e:
#             msg = f"Plugin {plugin_name} failed validation: {e}"
#             logger.warning(msg)
#             plugin_config['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': msg}
#         except ModuleNotFoundError as e:
#             msg = f"Failed to load {plugin_name}: {e}"
#             logger.warning(msg)
#             plugin_config['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': msg}
#         except Exception as e:
#             msg = f"Unexpected error adding {plugin_name}: {e}"
#             logger.error(msg)
#             plugin_config['plugin_status'] = {'status': self.LOAD_FAILED, 'reason': msg}

#         finally:
#             # Always track plugin configuration regardless of success/failure
#             if plugin_config not in self._configured_plugins:
#                 self._configured_plugins.append(plugin_config)
        
#         return False
        
#     # ----- Plugin Cycling and Management
#     def update_plugins(self):
#         """
#         Update all active plugins and check dormant plugins for activation.
#         The foreground_plugin displays until its timer expires or a dormant plugin 
#         activates as high-priority and interrupts the display.
#         """
#         logger.info('---------- Updating Plugins ----------')
#         if not self.foreground_plugin:
#             self.foreground_plugin = self.active_plugins[0]
#         # Update the foreground plugin if it's time
#         if self.foreground_plugin and self.foreground_plugin.ready_for_update:
#             logger.info(f"Updating foreground plugin: {self.foreground_plugin.name}")
#             try:
#                 success = self.foreground_plugin.update()
#                 if success:
#                     # Reset failure count on success for foreground plugin
#                     self.plugin_failures[self.foreground_plugin.uuid] = 0
#                 else:
#                     self._handle_plugin_failure(self.foreground_plugin)
#             except Exception as e:
#                 logger.error(f"Error updating {self.foreground_plugin.name}: {e}")
#                 self._handle_plugin_failure(self.foreground_plugin)
    
#         # Always check dormant plugins for activation
#         for plugin in self.dormant_plugins:
#             if plugin.ready_for_update:
#                 logger.info(f"Checking dormant plugin: {plugin.name}")
#                 try:
#                     success = plugin.update()
#                     if success:
#                         # Reset failure count on success for dormant plugins
#                         self.plugin_failures[plugin.uuid] = 0
        
#                         if plugin.high_priority:
#                             logger.info(f"{plugin.name} activated as high-priority.")
#                             self.foreground_plugin = plugin
#                             break
#                     else:
#                         self._handle_plugin_failure(plugin)
#                 except Exception as e:
#                     logger.error(f"Error updating dormant plugin {plugin.name}: {e}")
#                     self._handle_plugin_failure(plugin)
    
#         # Cycle to the next plugin if the foreground_plugin timer has expired
#         if self.foreground_plugin and self.foreground_plugin.time_to_refresh <= 0:
#             logger.info(f"{self.foreground_plugin.name} cycle complete. Moving to next plugin.")
#             self._cycle_to_next_plugin()

#     def _handle_plugin_failure(self, plugin):
#         """
#         Track and handle plugin update failures.

#         Increments the failure count for the specified plugin. If the failure count
#         exceeds the configured `max_plugin_failures`, the plugin is removed from
#         the manager. Logs warnings for each failure and upon plugin removal.

#         Args:
#             plugin (BasePlugin): The plugin instance that encountered a failure.

#         Raises:
#             KeyError: If the plugin does not have a UUID (unexpected scenario).
#         """
#         uuid = plugin.uuid
#         self.plugin_failures[uuid] = self.plugin_failures.get(uuid, 0) + 1
        
#         if self.plugin_failures[uuid] >= self.max_plugin_failures:
#             logger.warning(f"{plugin.name} removed after {self.max_plugin_failures} consecutive failures.")
#             self._remove_plugin_by_uuid(uuid)
#         else:
#             logger.warning(f"{plugin.name} failed ({self.plugin_failures[uuid]}/{self.max_plugin_failures}).")

# +
# # ! ln -s ../plugins ./

# +
# m = PluginManager()

# m.plugin_path = './plugins/'
# m.config_path = '../config/'
# m.main_schema_file = 'plugin_manager_schema.yaml'
# m.plugin_schema_file = 'plugin_schema.yaml'

# config = {
#     'screen_mode': 'L',
#     'resolution': (300, 160),
# }

# configured_plugins = [
#     {'plugin': 'basic_clock',
#          'base_config': {
#             'name': 'Basic Clock',
#             'duration': 100,
#             # 'refresh_interval': 60,
#             # 'dormant': False,
#             'layout_name': 'layout',
#          }
#     },
#     # {'plugin': 'debugging',
#     #     'base_config': {
#     #         'name': 'Debugging 50',
#     #         'dormant': True,
#     #         'layout': 'layout',
#     #         'refresh_interval': 2,
#     #     },
#     #     'plugin_params': {
#     #         'title': 'Debugging 50',
#     #         'crash_rate': 0.9,
#     #         'high_priority_rate': 0.2,
            
#     #     }
#     # },
#     {'plugin': 'word_clock',
#         'base_config':{
#             'name': 'Word Clock',
#             'duration': 130,
#             'refresh_interval': 60,
#             'layout_name': 'layout',
#         },
#         'plugin_params': {
#             'foo': 'bar',
#             'spam': 7,
#             'username': 'Monty'}
#     },
#     # {'plugin': 'xkcd_comic',
#     #     'base_config': {
#     #         'name': 'XKCD',
#     #         'duration': 200,
#     #         'refresh_interval': 1800,
#     #         'dormant': False,
#     #         'layout': 'layout'
#     #     },
#     #     'plugin_params':{
#     #         'max_x': 800,
#     #         'max_y': 600,
#     #         'resize': False,
#     #         'max_retries': 5
#     #     }
             
#     # }
# ]
# m.config = config

# # m.configured_plugins = configured_plugins
# # m.load_plugins()
