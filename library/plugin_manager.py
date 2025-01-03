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
# from importlib import import_module, util
import importlib.util
import sys
from time import monotonic



# -

try:
    # from .exceptions import PluginError, ImageError, PluginTimeoutError, FileError, ConfigurationError
    from .base_plugin import BasePlugin
except ImportError:
#     # support jupyter developement
#     from exceptions import PluginError, ImageError, PluginTimeoutError, FileError, ConfigurationError
    from base_plugin import BasePlugin

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
    CONFIG_FAILED = 'config_failed'
    CRASHED = 'crashed'
    PENDING = 'pending_validation'
    DEACTIVATED = 'deactivated'
    
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

        # track the currently displayed plugin and start time
        self.foreground_plugin: Optional[BasePlugin] = None
        self.foreground_start_time: float = 0.0

        # index for cycling among active plugins
        self._active_index: int = 0

        # keep track of consecutive failures per plugin
        self.plugin_failures: Dict[str, int] = {}
    
        
        logger.info("PluginManager initialized.")


    
    
    # SCHEMA LOADING
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

    
    # CONFIG PROPERTIES
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
    
    # PATHS and FILES
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

    # PLUGIN LISTS, SETTERS AND ASSOCIATED FUNCTIONS
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
        
    # PLUGIN LIFE-CYCLE AND UPDATING
    def add_plugin(self, plugin_config: dict, force_duplicate: bool = False):
        if not self.plugin_schema_file:
            raise FileNotFoundError("Plugin schema is required, but is not set.")
    
        plugin_id = plugin_config.get('plugin')
        if not plugin_id:
            raise ValueError("Plugin configuration does not contain a valid 'plugin' identifier.")
    
        plugin_name = plugin_config.get('plugin_config', {}).get('name', 'UNSET NAME')
    
        logger.info(f"Adding plugin {plugin_name} of type {plugin_id}...")
    
        plugin_status = {
            'status': self.PENDING,
            'reason': 'Pending validation'
        }
    
        plugin_schema_file_path = self.plugin_schema_file
        try:
            plugin_schema = self.load_schema(plugin_schema_file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"Base plugin schema file not found at {plugin_schema_file_path}")
    
        try:
            validated_plugin_config = self.validate_config(
                plugin_config.get('plugin_config', {}),
                plugin_schema
            )
        except ValueError:
            plugin_status['status'] = self.CONFIG_FAILED
            plugin_status['reason'] = 'Plugin config validation failed'
            logger.error(f"Plugin config validation failed for {plugin_name}")
            raise
    
        try:
            plugin_param_schema_file = self.plugin_path / plugin_id / self.plugin_param_filename
            plugin_param_schema = self.load_schema(plugin_param_schema_file, cache=False)
        except FileNotFoundError:
            logger.debug(f"Parameters schema file not found for plugin '{plugin_id}'. Assuming none required.")
            plugin_param_schema = {}
    
        plugin_params = plugin_config.get('plugin_params', {})
        try:
            validated_plugin_params = self.validate_config(plugin_params, plugin_param_schema)
        except ValueError:
            plugin_status['status'] = self.CONFIG_FAILED
            plugin_status['reason'] = 'Plugin params validation failed'
            logger.error(f"Plugin params validation failed for {plugin_id}")
            raise
    
        if validated_plugin_config.get('dormant', False):
            plugin_status.update(status=self.DORMANT, reason='Configuration validated (dormant)')
        else:
            plugin_status.update(status=self.ACTIVE, reason='Configuration validated')
    
        plugin_uuid = str(uuid4())[:8]
    
        final_config = {
            'plugin': plugin_id,
            'plugin_config': validated_plugin_config,
            'plugin_params': validated_plugin_params,
            'uuid': plugin_uuid,
            'plugin_status': plugin_status
        }
    
        # Duplicate check
        if not force_duplicate:
            new_signature = self.plugin_config_signature(final_config)
            for existing_plugin in self.configured_plugins:
                if self.plugin_config_signature(existing_plugin) == new_signature:
                    logger.info(
                        f"Duplicate detected: Plugin '{plugin_id}' already exists. Skipping addition."
                    )
                    return  # Early return to avoid adding duplicate
    
        self.configured_plugins.append(final_config)
        logger.info(
            f"Plugin '{plugin_id}' added with UUID={plugin_uuid} and status={plugin_status['status']}."
        )
        return final_config

    def add_plugins(self, plugin_configs: list[dict], force_duplicate: bool = False):
        """
        Add multiple plugin configurations to the list of configured plugins.
    
        Args:
            plugin_configs (list[dict]): A list of plugin configurations to validate and add.
            force_duplicate (bool): If True, allows duplicate plugins to be added.
    
        Returns:
            dict: A summary containing the number of successful and failed plugin additions.
        """
        results = {
            'added': 0,
            'failed': 0,
            'duplicated': 0,
            'failures': [],
            'duplicate_config': [],           
        }
    
        for plugin_config in plugin_configs:
            plugin_id = plugin_config.get('plugin', 'UNKNOWN')
            try:
                returned_config = self.add_plugin(plugin_config, force_duplicate=force_duplicate)
                if returned_config:
                    results['added'] += 1
                else:
                    results['duplicated'] += 1
                    results['duplicate_config'].append({
                        'plugin': plugin_id,
                        'reason': 'Duplicate plugin with identical configuration found.'
                    })
            except (ValueError, FileNotFoundError) as e:
                # Mark the plugin as failed, but add to the list with status CONFIG_FAILED
                plugin_status = {
                    'status': self.CONFIG_FAILED,
                    'reason': str(e)
                }
                plugin_uuid = str(uuid4())[:8]
    
                failed_config = {
                    'plugin': plugin_id,
                    'plugin_config': plugin_config.get('plugin_config', {}),
                    'plugin_params': plugin_config.get('plugin_params', {}),
                    'uuid': plugin_uuid,
                    'plugin_status': plugin_status
                }
    
                self.configured_plugins.append(failed_config)
                results['failed'] += 1
                results['failures'].append({
                    'plugin': plugin_id,
                    'reason': str(e)
                })
    
                logger.warning(
                    f"Plugin '{plugin_id}' failed to add. Reason: {str(e)}"
                )
    
        logger.info(
            f"Plugin batch processing completed. Added: {results['added']}, "
            f"Failed: {results['failed']}."
        )
    
        return results
        
    def remove_plugin_config(self, uuid: str) -> bool:
        """
        Remove a plugin configuration by its UUID.
    
        Args:
            uuid (str): The UUID of the plugin to remove.
    
        Returns:
            bool: True if the plugin was removed, False if no match was found.
        """
        for i, plugin in enumerate(self.configured_plugins):
            if plugin.get('uuid') == uuid:
                removed_plugin = self.configured_plugins.pop(i)
                logger.info(f"Plugin '{removed_plugin['plugin']}' with UUID={uuid} removed.")
                return True
        
        logger.warning(f"No plugin with UUID={uuid} found.")
        return False
        
    def activate_plugin_by_uuid(self, uuid: str, status: str, reason = None) -> bool:
        """
        Activate a configured plugin by UUID and set its status as active or dormant

        Returns:
            bool: True if successfully activated
        """
        success = False
        if not status in (self.ACTIVE, self.DORMANT):
            logger.error(f"Valid status values for activated plugins are: {self.ACTIVE, self.DORMANT}")
            return False
        
        if not reason:
            reason = 'Activated by UUID'
        
        for config in self.configured_plugins:
            config_uuid = config.get('uuid')    
            if config_uuid == uuid:
                plugin_status = config.get('plugin_status', {})
                plugin_status['status'] = status
                plugin_status['reason'] = reason
                config['plugin_status'] = plugin_status
                
                if self.load_plugin(config):
                    success = True
        return success
                
    
    def deactivate_plugin_by_uuid(self, uuid: str, status: str = None, reason: str = None) -> bool:
        """
        Deactivate a plugin instance by UUID from the active or dormant lists.

        Args:
            uuid (str): The UUID of the plugin to remove.

        Returns:
            bool: True if a plugin instance was removed, False if no match was found.
        """
        success = False
        if not status:
            status = self.DEACTIVATED

        if not reason:
            reason = 'Plugin removed - no reason given'
        
        # Search and remove from active plugins
        for i, plugin in enumerate(self.active_plugins):
            if plugin.uuid == uuid:
                removed_plugin = self.active_plugins.pop(i)
                logger.info(f"Removed active plugin '{removed_plugin.name}' (UUID={uuid}).")
                success = True

        # Search and remove from dormant plugins
        for i, plugin in enumerate(self.dormant_plugins):
            if plugin.uuid == uuid:
                removed_plugin = self.dormant_plugins.pop(i)
                logger.info(f"Removed dormant plugin '{removed_plugin.name}' (UUID={uuid}).")
                success = True

        if success:
            for config in self.configured_plugins:
                if config.get('uuid') == uuid:
                    status = {'status': status,
                              'reason': reason}
                    config['plugin_status'] = status
                    break
        
        logger.warning(f"No active/dormant plugin with UUID={uuid} found.")
        return success

    def delete_plugin(self, uuid: str) -> bool:
        """
        Fully remove a plugin by UUID from active/dormant lists and configuration.

        Args:
            uuid (str): The UUID of the plugin to delete.

        Returns:
            bool: True if the plugin was removed from either the lists or config, False if not found.
        """
        removed_from_plugins = self.deactivate_plugin_by_uuid(uuid)
        removed_from_config = self.remove_plugin_config(uuid)

        if removed_from_plugins or removed_from_config:
            logger.info(f"Plugin with UUID={uuid} fully deleted.")
            return True
        
        logger.warning(f"Failed to delete plugin with UUID={uuid}. Not found in plugins or config.")
        return False
    
    def plugin_config_signature(self, plugin_config: dict) -> str:
        """Generate a hash signature of a plugin config, ignoring transient fields."""
        cfg = dict(plugin_config)
    
        # Ensure deep copy to avoid modifying the original
        cfg['plugin_config'] = dict(cfg.get('plugin_config', {}))
        cfg['plugin_params'] = dict(cfg.get('plugin_params', {}))
    
        # Remove transient fields
        for key in self._transient_config_keys:
            cfg.pop(key, None)
    
        # Convert to JSON for consistent ordering and hash it
        cfg_json = json.dumps(cfg, sort_keys=True)
        return hashlib.md5(cfg_json.encode('utf-8')).hexdigest()

    def load_plugin(self, entry: dict) -> Optional[BasePlugin]:
        """
        Load a single plugin based on its configuration entry.
    
        Args:
            entry (dict): A single plugin config entry from self.configured_plugins.
    
        Returns:
            BasePlugin or None:
                - Returns a newly constructed BasePlugin if successful.
                - Returns None if we skip/ fail. (In that case, the function updates `entry["plugin_status"]`.)
        """
        plugin_status_info = entry.get("plugin_status", {})
        status = plugin_status_info.get("status", "").lower()
    
        # Only load if status is 'active' or 'dormant'
        if status not in (self.ACTIVE, self.DORMANT):
            logger.debug(f"Skipping plugin '{entry.get('plugin')}' with status='{status}'.")
            return None
    
        plugin_id  = entry.get("plugin", "unknown_plugin")
        plugin_uuid = entry.get("uuid")
        # Merge the plugin_params into plugin_config
        plugin_config = entry.get("plugin_config", {})
        plugin_params = entry.get("plugin_params", {})
        plugin_config["uuid"]   = plugin_uuid
        plugin_config["config"] = plugin_params
    
        # Ensure __init__.py exists
        plugin_dir  = self.plugin_path / plugin_id
        init_path   = plugin_dir / "__init__.py"
        if not init_path.is_file():
            reason = f"Plugin '{plugin_id}' does not contain __init__.py"
            logger.error(reason)
            entry["plugin_status"] = {"status": self.LOAD_FAILED, "reason": reason}
            return None
    
        # Dynamically load the plugin module from the filesystem
        try:
            spec = importlib.util.spec_from_file_location(plugin_id, str(init_path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[plugin_id] = module
            spec.loader.exec_module(module)
        except Exception as e:
            reason = f"Failed to load plugin '{plugin_id}': {e}"
            logger.exception(reason)
            entry["plugin_status"] = {"status": self.LOAD_FAILED, "reason": reason}
            return None
    
        # Load the layout
        layout_name = plugin_config.get("layout_name")
        if not layout_name:
            reason = f"Plugin '{plugin_id}' missing 'layout_name'."
            logger.warning(reason)
            entry["plugin_status"] = {"status": self.LOAD_FAILED, "reason": reason}
            return None
    
        try:
            update_function = getattr(module.plugin, "update_function")
        except AttributeError as e:
            reason = f"update_function not found in {plugin_id}/plugin.py: {e}"
            logger.warning(reason)
            entry["plugin_status"] = {"status": self.LOAD_FAILED, "reason": reason}
            return None
    
        try:
            layout_obj = getattr(module.layout, layout_name)
            plugin_config["layout"] = layout_obj
        except AttributeError as e:
            reason = f"Layout '{layout_name}' not found in plugin '{plugin_id}': {e}"
            logger.warning(reason)
            entry["plugin_status"] = {"status": self.LOAD_FAILED, "reason": reason}
            return None
        except Exception as e:
            reason = f"Unexpected error accessing layout '{layout_name}' in '{plugin_id}': {e}"
            logger.exception(reason)
            entry["plugin_status"] = {"status": self.LOAD_FAILED, "reason": reason}
            return None
    
        # Check duplicates
        for p in self.active_plugins + self.dormant_plugins:
            if p.uuid == plugin_uuid:
                logger.warning("Plugin with duplicate UUID already configured. Will not add duplicate.")
                return None
    
        # Attempt to instantiate BasePlugin
        try:
            plugin_instance = BasePlugin(**plugin_config)
            plugin_instance.update_function = update_function
        except Exception as e:
            reason = f"Error creating BasePlugin for '{plugin_id}' (UUID={plugin_uuid}): {e}"
            logger.error(reason)
            entry["plugin_status"] = {"status": self.LOAD_FAILED, "reason": reason}
            return None
    
        # Success path: return the constructed plugin
        return plugin_instance


    def load_plugins(self) -> None:
        """
        Fresh load all configured active/dormant plugins based on 
        self.configured_plugins entries.
    
        Clears out any existing active/dormant plugin references in
        self.active_plugins, self.dormant_plugins, and tries to load
        each plugin via load_plugin().
    
        If a plugin is loaded successfully, updates plugin_status in the
        config entry and places it into the appropriate list.
        If any failure occurs, plugin_status is updated to 'load_failed'.
        """
        # Clear old references
        self.active_plugins.clear()
        self.dormant_plugins.clear()
    
        for entry in self.configured_plugins:
            # Attempt to load a single plugin
            plugin_obj = self.load_plugin(entry)
            if plugin_obj is None:
                # The method sets plugin_status to LOAD_FAILED if it was needed
                continue
    
            # We have a plugin_obj. Decide if it’s active or dormant
            if plugin_obj.dormant:
                self.dormant_plugins.append(plugin_obj)
                entry["plugin_status"] = {
                    "status": self.DORMANT,
                    "reason": "Loaded as dormant",
                }
                logger.info(f"Loaded dormant plugin '{entry.get('plugin')}' (UUID={plugin_obj.uuid}).")
            else:
                self.active_plugins.append(plugin_obj)
                entry["plugin_status"] = {
                    "status": self.ACTIVE,
                    "reason": "Loaded as active",
                }
                logger.info(f"Loaded active plugin '{entry.get('plugin')}' (UUID={plugin_obj.uuid}).")
    
        logger.info(
            f"load_plugins complete: {len(self.active_plugins)} active, "
            f"{len(self.dormant_plugins)} dormant."
        )

    def _pick_next_active_plugin(self):
        """Select the next plugin from the active_plugins property in round-robin order"""

        if not self.active_plugins:
            self.foreground_plugin = None
            self._active_index = 0
            return

        # handle out of range indexes by resetting to the 0th
        if self._active_index >= len(self.active_plugins):
            self._active_index = 0

        # use the _active_index to choose the next plugin
        chosen = self.active_plugins[self._active_index]
        self.foreground_plugin = chosen
        
        self.foreground_start_time = monotonic()

        logger.info(f"Foreground plugin set to '{chosen.name}, and will display for {chosen.duration}' seconds")

        # advance the index
        self._active_index = (self._active_index + 1) % len(self.active_plugins)


    def _safe_plugin_update(self, plugin, force=False):
        """
        Safely update a plugin, handling exceptions and failure counts.

        Returns:
            dict: update status of plugin
        """
        success = {}
        uuid = plugin.uuid
        name = plugin.name
        logger.debug(f"Safe-updating plugin {name}, UUID: {uuid}")
        try:
            success = plugin.update(force)
            if success:
                # reset failure count
                self.plugin_failures[uuid] = 0 
                return success
            else:
                # Update failed, but no exception
                self.plugin_failures[uuid] = self.plugin_failures.get(uuid, 0) + 1
                logger.warning(f"{plugin.name}, uuid: {plugin.uuid} failed to update."
                               f"consecutive failures={self.plugin_failures[uuid]}")
        except Exception as e:
            self.plugin_failure[uuid] = self.plugin_failures.get(uuid, 0) + 1
            logger.error(f"Exception during {plugin.name}, uuid: {plugin.uuid} update: {e}", exc_info=True)

        # Check failure threshold
        if self.plugin_failures[uuid] >= self.max_plugin_failures:
            logger.warning(f"{plugin.name}, uuid: {plugin.uuid} removed after {self.max_plugin_failures} consecutive failures. ")
            # remove plugin from active list and set status as CRASHED in config
            reason = F"Plugin {name}, UUID: {uuid} failed to update {self.max_plugin_failures}"
            self.deactivate_plugin_by_uuid(uuid, status=self.CRASHED, reason=reason)
            logger.warning(reason)
        # return False
        return success

    def list_plugins(self):
        """
        List plugins based on type

        """
        plugin_dict ={}
        for p in self.configured_plugins:
            plugin_status = p.get('plugin_status', {})
            status = plugin_status.get('status')
            plugin_id = p.get('plugin', 'unknown')
            name = p.get('plugin_config', {}).get('name')
            uuid = p.get('uuid', 'no uuid set')
            if status in ('dormant', 'active'):
                tag = status
            else:
                tag = 'other'
            if not plugin_dict.get(tag, None):
                plugin_dict[tag] = {}
            plugin_dict[tag][uuid] = {'plugin': plugin_id,
                                'name': name,
                                'uuid': uuid,
                                'plugin_status': plugin_status}
            
        return plugin_dict
    
    def update_cycle(self, force_update=False, force_cycle=False) -> None:
        # this needs work, if the foreground plugin crashes on update, there should be some mechanism to pick another
        """
        Method for updating plugins and foregrounding active plugins

        
        """
        # if there is no foreground plugin, pick the next active plugin
        if not self.foreground_plugin:
            self._pick_next_active_plugin()
            if not self.foreground_plugin:
                logger.debug("No active plugins avaialble to foreground")
                return

        # attempt to update the foreground plugin
        if self.foreground_plugin.ready_for_update or force_update:
            logger.debug(f"Updating foreground plugin: {self.foreground_plugin.name}")
            success = self._safe_plugin_update(self.foreground_plugin, force_update)
            if not success:
                # implement removing or skipping this plugin
                # logger.debug("Foreground plugin update failed. Future logic: remove or skip.")
        else:
            logger.debug(f"Plugin {self.foreground_plugin.name} not ready for update; wait {self.foreground_plugin.time_to_refresh:.2f} seconds.")

        display_timer = abs(monotonic() - self.foreground_start_time)
        
        if display_timer >= self.foreground_plugin.duration or force_cycle:
            logger.info(f"Display ended for {self.foreground_plugin.name} due to {'forced cycle' if force_cycle else 'elapsed timer'}.")
            self._pick_next_active_plugin()
            self._safe_plugin_update(self.foreground_plugin)
        else:
            logger.info(f"{self.foreground_plugin.name} displaying for {abs(display_timer - self.foreground_plugin.duration):.2f} more seconds")


        # poll dormant plugins; if they become high-priority, foreground
        for plugin in self.dormant_plugins:
            if plugin.ready_for_update or force_update:
                success = self._safe_plugin_update(plugin, force_update)
                if success and plugin.high_priority:
                    logger.info(
                        f"Dormant plugin '{plugin.name}', '{plugin.uuid}' signaled high_priority. "
                        f"Replacing foreground plugin '{self.foreground_plugin.name}' with '{plugin.name}'"
                    )
                    self.foreground_plugin = plugin
                    self.foreground_start_time = monotonic()
                    self.foreground_plugin.high_priority = False
                    # this will only show the highest priority plugin
                    break


