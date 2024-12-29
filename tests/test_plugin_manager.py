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

import unittest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
import logging
import yaml

try:
    from paperpi.library.plugin_manager import PluginManager
    from paperpi.library.exceptions import *
except ModuleNotFoundError:
    from library.plugin_manager import PluginManager
    from library.exceptions import *

logger = logging.getLogger("PluginManager")
logger.setLevel(logging.WARNING)


# -------------------------------------------------------------------
# 1) TEST INITIALIZATION & BASIC PROPERTIES
# -------------------------------------------------------------------
class TestPluginManagerInitialization(unittest.TestCase):
    """Focus on how the PluginManager initializes and basic property checks."""

    def test_initialization_defaults(self):
        """Test that PluginManager initializes with default values."""
        manager = PluginManager()
        self.assertEqual(manager.config, {})
        self.assertIsNone(manager.plugin_path)
        self.assertIsNone(manager.config_path)
        self.assertEqual(manager.configured_plugins, [])
        self.assertEqual(manager.active_plugins, [])
        self.assertEqual(manager.dormant_plugins, [])

    def test_initialization_custom(self):
        """Test initialization with custom values."""
        config = {'debug': True}
        plugin_path = Path('/plugins')
        config_path = Path('/config')
        
        manager = PluginManager(
            config=config,
            plugin_path=plugin_path,
            config_path=config_path
        )
        
        self.assertEqual(manager.config, config)
        self.assertEqual(manager.plugin_path, plugin_path)
        self.assertEqual(manager.config_path, config_path)
        self.assertEqual(manager.configured_plugins, [])
        self.assertEqual(manager.active_plugins, [])
        self.assertEqual(manager.dormant_plugins, [])

    def test_empty_lists_on_init(self):
        """Ensure active and dormant plugins start as empty lists."""
        manager = PluginManager()
        self.assertIsInstance(manager.active_plugins, list)
        self.assertIsInstance(manager.dormant_plugins, list)
        self.assertEqual(len(manager.active_plugins), 0)
        self.assertEqual(len(manager.dormant_plugins), 0)

    def test_default_list_isolation(self):
        """Test that each PluginManager instance has isolated lists."""
        manager1 = PluginManager()
        manager2 = PluginManager()
        
        manager1.active_plugins.append("plugin1")
        self.assertNotIn("plugin1", manager2.active_plugins)

    def test_config_is_copied(self):
        """Ensure config is copied during initialization."""
        config = {'debug': True}
        manager = PluginManager(config=config)
        
        config['debug'] = False  # Modify original dict
        self.assertTrue(manager.config['debug'])  # Should remain True

    def test_none_config_defaults_to_empty_dict(self):
        """Ensure None for config defaults to empty dictionary."""
        manager = PluginManager(config=None)
        self.assertEqual(manager.config, {})


# -------------------------------------------------------------------
# 2) TEST PATH SETTERS AND VALIDATION
# -------------------------------------------------------------------
class TestPluginManagerPathHandling(unittest.TestCase):
    """Focus on plugin_path and config_path validation & behavior."""

    def setUp(self):
        self.manager = PluginManager()  # Fresh instance per test

    def test_valid_paths(self):
        """Test that valid paths are accepted."""
        path = Path("/valid/path")
        self.manager.plugin_path = path
        self.manager.config_path = path
        
        self.assertEqual(self.manager.plugin_path, path)
        self.assertEqual(self.manager.config_path, path)

    def test_invalid_path_type(self):
        """Test that invalid path types raise TypeError."""
        with self.assertRaises(TypeError):
            self.manager.config_path = 12345  # Invalid type

        # If you want to test that string -> Path conversion is allowed:
        self.manager.plugin_path = "some/string/path"
        self.assertEqual(self.manager.plugin_path, Path("some/string/path"))

        # If you want to ensure None is allowed:
        self.manager.plugin_path = None
        self.assertIsNone(self.manager.plugin_path)


class TestPluginManagerSignatures(unittest.TestCase):
    """Test plugin config signature generation and comparison."""

    def setUp(self):
        self.manager = PluginManager()

    def test_plugin_config_signature(self):
        """Ensure plugin_config_signature generates consistent hashes."""
        plugin_config_1 = {
            'plugin': 'clock',
            'refresh_interval': 30,
            'uuid': '12345'  # Should be ignored in signature
        }
        plugin_config_2 = {
            'plugin': 'clock',
            'refresh_interval': 30,
            'uuid': '67890'  # Different uuid, but same config
        }
        
        signature_1 = self.manager.plugin_config_signature(plugin_config_1)
        signature_2 = self.manager.plugin_config_signature(plugin_config_2)
        
        self.assertEqual(signature_1, signature_2)


# -------------------------------------------------------------------
# 3) TEST SCHEMA LOADING (FILE OPERATIONS)
# -------------------------------------------------------------------
class TestPluginManagerSchemaLoading(unittest.TestCase):
    """Focus on how the PluginManager loads schema files from disk."""

    def setUp(self):
        # Provide a valid config_path so that load_schema can find files
        self.manager = PluginManager(config_path=Path("/tmp"))

    def test_load_schema_without_config_path(self):
        """Test loading schema without setting config_path."""
        self.manager.config_path = None
        with self.assertRaises(FileNotFoundError):
            self.manager.load_schema('base_schema.yaml')

    @patch('pathlib.Path.is_file', return_value=False)
    def test_load_schema_file_not_found(self, mock_is_file):
        """Test loading schema when the schema file is missing."""
        with self.assertRaises(FileNotFoundError):
            self.manager.load_schema('missing_schema.yaml')

    @patch('builtins.open', new_callable=mock_open, read_data="invalid_yaml: [unbalanced_bracket")
    def test_load_schema_malformed_yaml(self, mock_file):
        """Test error handling when schema contains invalid YAML."""
        # Path.is_file => True to simulate the file exists
        with patch('pathlib.Path.is_file', return_value=True):
            with self.assertRaises(ValueError):
                self.manager.load_schema('malformed_schema.yaml')

    @patch('pathlib.Path.is_file', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({'key': 'value'}))
    def test_load_schema_with_cache(self, mock_file, mock_is_file):
        """Test that schema is cached when cache=True (default)."""
        schema_path = Path('/tmp/base_schema.yaml')
        self.manager.load_schema(schema_path)  # Default: cache=True

        # Ensure schema is now cached
        self.assertIn(schema_path.resolve(), self.manager._schema_cache)

    @patch('pathlib.Path.is_file', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({'key': 'value'}))
    def test_load_schema_no_cache(self, mock_file, mock_is_file):
        """Test that schema is not cached when cache=False."""
        schema_path = Path('/tmp/base_schema.yaml')
        self.manager.load_schema(schema_path, cache=False)

        # Verify schema is NOT cached
        self.assertNotIn(schema_path.resolve(), self.manager._schema_cache)

    @patch('pathlib.Path.is_file', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({'key': 'value'}))
    def test_load_schema_force_reload(self, mock_file, mock_is_file):
        """Test forcing schema reload from disk when cache=False, even if it exists in cache."""
        schema_path = Path('/tmp/base_schema.yaml')

        # Load schema with caching first
        self.manager.load_schema(schema_path)  # cache=True by default

        # Confirm schema is cached
        self.assertIn(schema_path.resolve(), self.manager._schema_cache)

        # Force reload (cache=False)
        with patch.object(self.manager, '_schema_cache', {schema_path.resolve(): {'cached_key': 'cached_value'}}):
            schema = self.manager.load_schema(schema_path, cache=False)

        # Ensure the schema loaded from disk (not cache)
        self.assertEqual(schema, {'key': 'value'})


class TestPluginManagerPluginSchema(unittest.TestCase):
    """Tests to validate plugin schema file interaction."""

    @patch("pathlib.Path.is_file", return_value=True)
    def setUp(self, mock_is_file):
        self.mock_plugin_schema = {
            'refresh_rate': {'type': 'int', 'default': 60},
            'enabled': {'type': 'bool', 'default': True}
        }

        # Mock load_schema for plugin schema validation
        self.load_schema_patcher = patch.object(
            PluginManager,
            'load_schema',
            return_value=self.mock_plugin_schema
        )
        self.mock_load_schema = self.load_schema_patcher.start()

        self.manager = PluginManager(
            config_path=Path('/tmp'),
            plugin_schema_file='plugin_schema.yaml'
        )

    def tearDown(self):
        self.load_schema_patcher.stop()

    @patch("pathlib.Path.is_file", return_value=False)
    def test_plugin_schema_file_not_found(self, mock_is_file):
        """Test that plugin_schema_file raises FileNotFoundError if file is missing."""
        with self.assertRaises(FileNotFoundError):
            self.manager.plugin_schema_file = 'missing_plugin_schema.yaml'

    @patch("pathlib.Path.is_file", return_value=True)
    def test_plugin_schema_file_sets_correctly(self, mock_is_file):
        """Test that plugin_schema_file resolves correctly when the file exists."""
        self.manager.plugin_schema_file = 'plugin_schema.yaml'
        expected_path = Path('/tmp/plugin_schema.yaml')
        self.assertEqual(self.manager.plugin_schema_file, expected_path)

    @patch("pathlib.Path.is_file", return_value=False)
    def test_plugin_schema_no_config_path(self, mock_is_file):
        """Ensure no error is raised if config_path is None when setting plugin_schema_file."""
        self.manager.config_path = None
        # No FileNotFoundError should be raised because config_path is None
        self.manager.plugin_schema_file = 'plugin_schema.yaml'
        self.assertEqual(self.manager.plugin_schema_file, 'plugin_schema.yaml')

    def test_plugin_schema_loads_from_cache(self):
        """Ensure plugin schema loads from cache if already present."""
        # Inject a schema into _schema_cache to simulate prior load
        cached_schema = {
            'refresh_rate': {'type': 'int', 'default': 30}
        }
        self.manager._schema_cache['plugin_schema.yaml'] = cached_schema

        # Re-assign the same schema file => should load from cache
        self.manager.plugin_schema_file = 'plugin_schema.yaml'

        # Load schema should not be triggered; it uses the cached version
        self.mock_load_schema.assert_not_called()

    @patch("pathlib.Path.is_file", return_value=True)
    def test_plugin_schema_overwrites(self, mock_is_file):
        """Ensure setting plugin_schema_file overwrites the previous value."""
        self.manager.plugin_schema_file = 'plugin_schema.yaml'
        self.assertEqual(self.manager.plugin_schema_file, Path('/tmp/plugin_schema.yaml'))

        # Overwrite with a new schema
        self.manager.plugin_schema_file = 'new_plugin_schema.yaml'
        self.assertEqual(self.manager.plugin_schema_file, Path('/tmp/new_plugin_schema.yaml'))


# -------------------------------------------------------------------
# 4) TEST CONFIG VALIDATION & SCHEMA INTERACTION
# -------------------------------------------------------------------
class TestPluginManagerConfigValidation(unittest.TestCase):

    @patch("pathlib.Path.is_file", return_value=True)
    def setUp(self, mock_is_file):
        # Now is_file() always returns True, so the property setter won't raise.
        self.mock_base_schema = {
            'screen_mode': {'type': 'str', 'default': '1', 'allowed': ['1', 'L', 'RGB'], 'required': True},
            'resolution': {'type': 'tuple', 'default': (800, 480)},
            'cache_expire': {'type': 'int', 'default': 2},
        }

        # Mock load_schema to return self.mock_base_schema
        self.load_schema_patcher = patch.object(
            PluginManager,
            'load_schema',
            return_value=self.mock_base_schema
        )
        self.mock_load_schema = self.load_schema_patcher.start()

        self.initial_config = {
            'screen_mode': 'L',
            'resolution': (600, 400),
            'cache_expire': 5
        }

        self.manager = PluginManager(
            config=self.initial_config,
            base_schema_file='base_schema.yaml',
            config_path=Path('/tmp')
        )

    def tearDown(self):
        self.load_schema_patcher.stop()

    def test_config_defaults_applied(self):
        """Test defaults are applied if config is missing values."""
        partial_config = {'screen_mode': 'RGB'}
        self.manager.config = partial_config
        # 'cache_expire' => 2, 'resolution' => (800, 480) from mock_schema
        self.assertEqual(self.manager.config['cache_expire'], 2)
        self.assertEqual(self.manager.config['resolution'], (800, 480))

    def test_valid_config_passes(self):
        """Ensure valid config passes validation."""
        # Overwrite config with the manager.config setter
        self.manager.config = self.initial_config
        self.assertEqual(self.manager.config['screen_mode'], 'L')
        self.assertEqual(self.manager.config['resolution'], (600, 400))
        self.assertEqual(self.manager.config['cache_expire'], 5)

    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
        'screen_mode': {'type': 'str', 'allowed': ['1', 'L', 'RGB'], 'required': True},
    }))
    def test_invalid_config_value(self, mock_file):
        """Test invalid config value raises a validation error."""
        invalid_config = {'screen_mode': 42}  # Should be str, not int
        with self.assertRaises(ValueError):
            self.manager.config = invalid_config

    def test_missing_required_config(self):
        """Ensure missing required config raises an error."""
        # Suppose 'screen_mode' is required in self.mock_base_schema
        # We'll remove it from the new config:
        incomplete_config = {'cache_expire': 10}  # Missing 'screen_mode'
        
        with self.assertRaises(ValueError):
            self.manager.config = incomplete_config

    def test_config_overwrite(self):
        """Ensure overwriting config triggers validation."""
        new_config = {'screen_mode': 'L', 'cache_expire': 7}
        self.manager.config = new_config
        # check we used the new config
        self.assertEqual(self.manager.config['cache_expire'], 7)

    def test_schema_loads_from_cache(self):
        """Ensure schema is loaded from cache if available."""
        # Inject a new schema into _schema_cache
        alt_schema = {
            'cache_expire': {'type': 'int', 'default': 2}
        }
        self.manager._schema_cache['base_schema.yaml'] = alt_schema

        # Re-assign config => triggers the config setter => uses the cached schema
        test_config = {'screen_mode': 'L', 'cache_expire': 10}
        self.manager.config = test_config

        # Confirm we see the config's overridden value, not the alt_schema default
        # Because 'cache_expire' is indeed set to 10, and alt_schema would default it to 2 if missing
        self.assertEqual(self.manager.config['cache_expire'], 10)


# +
# -------------------------------------------------------------------
# 5) TEST PLUGIN MANAGEMENT (CONFIGURED PLUGINS)
# -------------------------------------------------------------------

# this needs attention - structure will change

class TestPluginManagerPlugins(unittest.TestCase):
    """Focus on setting configured_plugins and verifying structure."""

    def setUp(self):
        self.manager = PluginManager()

    def test_plugin_list_validation(self):
        """Ensure configured_plugins accepts valid list of dictionaries."""
        valid_plugins = [
            {"plugin": "weather_plugin", "base_config": {}},
            {"plugin": "news_plugin", "base_config": {}}
        ]
        self.manager.configured_plugins = valid_plugins
        self.assertEqual(len(self.manager.configured_plugins), 2)

    def test_invalid_plugin_structure(self):
        """Ensure configured_plugins raises error for invalid structures."""
        # Not a list
        with self.assertRaises(TypeError):
            self.manager.configured_plugins = "invalid_string"

        # List of invalid data
        with self.assertRaises(TypeError):
            self.manager.configured_plugins = [123, "string"]

        # Missing keys
        with self.assertRaises(ValueError):
            self.manager.configured_plugins = [
                {"base_config": {}},  # Missing 'plugin' 
                {"plugin": "plugin_without_config"}  # Missing 'base_config'
            ]

    def test_empty_plugins_list(self):
        """Ensure setting configured_plugins to an empty list doesn't fail."""
        self.manager.configured_plugins = []
        self.assertEqual(len(self.manager.configured_plugins), 0)


# -

class TestPluginManagerSchemaInteraction(unittest.TestCase):
    """Test interaction with plugin schema and param schema files."""

    def setUp(self):
        self.manager = PluginManager(plugin_path=Path("/plugins"))
        
        # Set plugin_schema_file to avoid FileNotFoundError
        self.manager.plugin_schema_file = 'plugin_schema.yaml'
        
        # Mock load_schema to return a base schema
        self.mock_base_schema = {
            'refresh_interval': {'type': 'int', 'default': 10}
        }
        patcher = patch.object(self.manager, 'load_schema', return_value=self.mock_base_schema)
        self.mock_load_schema = patcher.start()
        self.addCleanup(patcher.stop)

    def test_plugin_param_filename(self):
        """Ensure plugin_param_filename is used correctly for per-plugin schema."""
        plugin_config = {
            'plugin': 'weather',
            'plugin_params': {'units': 'metric'}
        }
        
        # Mock param schema file check to simulate a missing file
        with patch('pathlib.Path.is_file', return_value=False):
            self.manager.plugin_param_filename = 'custom_param_schema.yaml'
            
            # Test that add_plugin proceeds without param schema file
            self.manager.add_plugin(plugin_config)
            
            # Assert that the param filename is correctly set
            self.assertEqual(self.manager.plugin_param_filename, 'custom_param_schema.yaml')


class TestPluginManagerAddPlugin(unittest.TestCase):
    """Test add_plugin method for duplicate detection, schema validation, and forced adds."""

    def setUp(self):
        self.manager = PluginManager(plugin_path=Path("/plugins"))
        
        # Set plugin_schema_file to bypass initial FileNotFoundError
        self.manager.plugin_schema_file = 'plugin_schema.yaml'
        self.manager.plugin_param_filename = 'plugin_param_schema.yaml'

        # Base schema for validation
        self.mock_base_schema = {
            'refresh_interval': {'type': 'int', 'default': 10}
        }
        
        # Mock load_schema to return a base schema
        patcher = patch.object(self.manager, 'load_schema', return_value=self.mock_base_schema)
        self.mock_load_schema = patcher.start()
        self.addCleanup(patcher.stop)

    def test_add_plugin_success(self):
        """Ensure plugin is successfully added when schema exists."""
        plugin_config = {
            'plugin': 'clock',
            'plugin_config': {'refresh_interval': 30}
        }
        
        self.manager.add_plugin(plugin_config)
        self.assertEqual(len(self.manager.configured_plugins), 1)
        self.assertEqual(self.manager.configured_plugins[0]['plugin'], 'clock')

    def test_add_plugin_avoids_duplicates(self):
        """Ensure identical plugins are skipped unless forced."""
        plugin_config = {
            'plugin': 'clock',
            'plugin_config': {'refresh_interval': 30}
        }
        
        # Add first instance
        self.manager.add_plugin(plugin_config)
        initial_count = len(self.manager.configured_plugins)
        
        # Attempt to add identical plugin (should skip)
        self.manager.add_plugin(plugin_config)
        self.assertEqual(initial_count, len(self.manager.configured_plugins))
        
        # Force add duplicate
        self.manager.add_plugin(plugin_config, force_duplicate=True)
        self.assertEqual(initial_count + 1, len(self.manager.configured_plugins))

    def test_plugin_signature_uniqueness(self):
        """Ensure signature changes for different plugin configurations."""
        plugin1 = {
            'plugin': 'clock',
            'plugin_config': {'refresh_interval': 30}
        }
        
        plugin2 = {
            'plugin': 'clock',
            'plugin_config': {'refresh_interval': 60}
        }
        
        signature1 = self.manager.plugin_config_signature(plugin1)
        signature2 = self.manager.plugin_config_signature(plugin2)
        
        self.assertNotEqual(signature1, signature2)

    def test_add_plugin_missing_param_schema(self):
        """Ensure adding plugin works if param schema is missing."""
        plugin_config = {
            'plugin': 'weather',
            'plugin_params': {'units': 'metric'}
        }
        
        # Patch is_file to simulate missing param schema
        with patch('pathlib.Path.is_file', return_value=False):
            self.manager.add_plugin(plugin_config)
            
            # Verify the plugin was added despite missing param schema
            self.assertEqual(len(self.manager.configured_plugins), 1)
            
            # Assert plugin is correctly added and params are stored
            self.assertEqual(self.manager.configured_plugins[0]['plugin'], 'weather')
            self.assertEqual(self.manager.configured_plugins[0]['plugin_params']['units'], 'metric')

    def test_add_plugin_fails_without_base_schema(self):
        """Ensure add_plugin fails if plugin_schema_file is not set."""
        self.manager.plugin_schema_file = None
        
        plugin_config = {
            'plugin': 'clock',
            'plugin_config': {'refresh_interval': 30}
        }
        
        with self.assertRaises(FileNotFoundError):
            self.manager.add_plugin(plugin_config)

    def test_add_plugin_invalid_config(self):
        """Ensure add_plugin fails for invalid plugin config."""
        plugin_config = {
            'plugin': 'clock',
            'plugin_config': {'refresh_interval': 'invalid_string'}  # Should be int
        }
        
        with self.assertRaises(ValueError):
            self.manager.add_plugin(plugin_config)

    def test_param_schema_success(self):
        """Ensure plugin param schema is used if available."""
        plugin_config = {
            'plugin': 'clock',
            'plugin_params': {'color': 'blue'}
        }
        
        # Mock per-plugin schema to validate params
        mock_param_schema = {
            'color': {'type': 'str', 'allowed': ['blue', 'red']}
        }
        
        with patch.object(self.manager, 'load_schema', return_value=mock_param_schema):
            self.manager.add_plugin(plugin_config)
            self.assertEqual(len(self.manager.configured_plugins), 1)
            self.assertEqual(self.manager.configured_plugins[0]['plugin_params']['color'], 'blue')


class TestPluginManagerAddMultiplePlugins(unittest.TestCase):
    """Test add_plugins method for handling multiple plugin configurations."""

    def setUp(self):
        self.manager = PluginManager(plugin_path=Path("/plugins"))

        # Set plugin_schema_file to bypass initial schema check
        self.manager.plugin_schema_file = 'plugin_schema.yaml'

        # Mock base schema for validating plugin configs
        self.mock_base_schema = {
            'refresh_interval': {'type': 'int', 'default': 10},
            'dormant': {'type': 'bool', 'default': False}
        }
        
        patcher = patch.object(self.manager, 'load_schema', return_value=self.mock_base_schema)
        self.mock_load_schema = patcher.start()
        self.addCleanup(patcher.stop)

    def test_add_multiple_plugins_success(self):
        """Ensure multiple plugins are added successfully."""
        plugin_configs = [
            {'plugin': 'clock', 'plugin_config': {'refresh_interval': 30}},
            {'plugin': 'weather', 'plugin_config': {'units': 'metric'}}
        ]
        
        result = self.manager.add_plugins(plugin_configs)
        
        self.assertEqual(result['added'], 2)
        self.assertEqual(len(self.manager.configured_plugins), 2)

    def test_duplicate_plugin_skipped(self):
        """Ensure duplicate plugins are skipped unless forced."""
        plugin_configs = [
            {'plugin': 'clock', 'plugin_config': {'refresh_interval': 30}},
            {'plugin': 'clock', 'plugin_config': {'refresh_interval': 30}}
        ]
        
        result = self.manager.add_plugins(plugin_configs)
        
        self.assertEqual(result['added'], 1)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(len(self.manager.configured_plugins), 1)

    def test_force_duplicate_plugin(self):
        """Ensure forcing duplicates works."""
        plugin_configs = [
            {'plugin': 'clock', 'plugin_config': {'refresh_interval': 30}},
            {'plugin': 'clock', 'plugin_config': {'refresh_interval': 30}}
        ]
        
        result = self.manager.add_plugins(plugin_configs, force_duplicate=True)
        
        self.assertEqual(result['added'], 2)
        self.assertEqual(len(self.manager.configured_plugins), 2)



    def test_plugin_validation_failure(self):
        """Ensure plugin with invalid config is marked as failed."""
        plugin_configs = [{'plugin': 'weather', 'plugin_config': {'refresh_interval': 'invalid'}}]
        
        # Simulate validation failure
        with patch.object(self.manager, 'validate_config', side_effect=ValueError("Validation failed")):
            result = self.manager.add_plugins(plugin_configs)
        
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['failures'][0]['plugin'], 'weather')
        self.assertIn('Validation failed', result['failures'][0]['reason'])
        self.assertEqual(len(self.manager.configured_plugins), 1)
        self.assertEqual(self.manager.configured_plugins[0]['plugin_status']['status'], self.manager.CONFIG_FAILED)

    def test_plugin_missing_identifier(self):
        """Ensure plugins missing 'plugin' key fail."""
        plugin_configs = [{'plugin_config': {'refresh_interval': 30}}]
        
        result = self.manager.add_plugins(plugin_configs)
        
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['failures'][0]['plugin'], 'UNKNOWN')
        self.assertIn("Plugin configuration does not contain a valid", result['failures'][0]['reason'])
        self.assertEqual(len(self.manager.configured_plugins), 1)
        self.assertEqual(self.manager.configured_plugins[0]['plugin_status']['status'], self.manager.CONFIG_FAILED)

    def test_add_plugin_with_params_missing_schema(self):
        """Ensure plugin with params but missing schema does not fail."""
        plugin_configs = [
            {'plugin': 'weather', 'plugin_params': {'units': 'metric'}}
        ]

        with patch('pathlib.Path.is_file', return_value=False):
            result = self.manager.add_plugins(plugin_configs)
        
        self.assertEqual(result['added'], 1)
        self.assertEqual(len(self.manager.configured_plugins), 1)
        self.assertEqual(self.manager.configured_plugins[0]['plugin'], 'weather')
        self.assertEqual(self.manager.configured_plugins[0]['plugin_status']['status'], self.manager.ACTIVE)


class TestPluginManagerRemovePlugin(unittest.TestCase):
    def setUp(self):
        self.manager = PluginManager(plugin_path=Path("/plugins"))
        
        # Set plugin schema file to bypass schema-related errors
        self.manager.plugin_schema_file = 'plugin_schema.yaml'
        
        # Sample plugin configuration to add
        self.plugin_config = {
            'plugin': 'clock',
            'plugin_config': {'refresh_interval': 30}
        }
    
        # Mock schema to bypass validation
        self.mock_base_schema = {
            'refresh_interval': {'type': 'int', 'default': 10}
        }
        
        # Patch load_schema to avoid file operations
        patcher = patch.object(self.manager, 'load_schema', return_value=self.mock_base_schema)
        self.mock_load_schema = patcher.start()
        self.addCleanup(patcher.stop)
    
        # Add plugin during setup
        self.plugin = self.manager.add_plugin(self.plugin_config)

    def test_remove_existing_plugin(self):
        """Ensure plugin is removed by UUID when it exists."""
        result = self.manager.remove_plugin_config(self.plugin['uuid'])
        self.assertTrue(result)
        self.assertEqual(len(self.manager.configured_plugins), 0)

    def test_remove_nonexistent_plugin(self):
        """Ensure False is returned if UUID is not found."""
        result = self.manager.remove_plugin_config('nonexistent_uuid')
        self.assertFalse(result)
        self.assertEqual(len(self.manager.configured_plugins), 1)

    def test_remove_multiple_plugins(self):
        """Ensure only the plugin with matching UUID is removed if multiple plugins exist."""
        second_plugin_config = {
            'plugin': 'weather',
            'plugin_config': {'refresh_interval': 60}
        }
        second_plugin = self.manager.add_plugin(second_plugin_config)

        result = self.manager.remove_plugin_config(self.plugin['uuid'])
        self.assertTrue(result)
        self.assertEqual(len(self.manager.configured_plugins), 1)

        # Ensure the remaining plugin is the second one
        self.assertEqual(self.manager.configured_plugins[0]['plugin'], 'weather')

    def test_remove_plugin_with_dormant_status(self):
        """Ensure plugins marked as dormant can also be removed."""
        dormant_plugin_config = {
            'plugin': 'calendar',
            'plugin_config': {'dormant': True}
        }
        dormant_plugin = self.manager.add_plugin(dormant_plugin_config)

        result = self.manager.remove_plugin_config(dormant_plugin['uuid'])
        self.assertTrue(result)
        self.assertEqual(len(self.manager.configured_plugins), 1)

    def test_remove_plugin_from_empty_list(self):
        """Ensure False is returned if no plugins are configured."""
        self.manager.configured_plugins = []
        result = self.manager.remove_plugin_config(self.plugin['uuid'])
        self.assertFalse(result)


unittest.main(argv=[''], verbosity=2, exit=False)

# +
# 1) Create a test loader
loader = unittest.TestLoader()

# 2) Load tests from all your classes
suite = unittest.TestSuite()
suite.addTests(loader.loadTestsFromTestCase(TestPluginManagerInitialization))
suite.addTests(loader.loadTestsFromTestCase(TestPluginManagerPathHandling))
suite.addTests(loader.loadTestsFromTestCase(TestPluginManagerSchemaLoading))
suite.addTests(loader.loadTestsFromTestCase(TestPluginManagerConfigValidation))
suite.addTests(loader.loadTestsFromTestCase(TestPluginManagerPlugins))
suite.addTests(loader.loadTestsFromTestCase(TestPluginManagerPluginSchema))

# 3) Run the tests
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

# +
# unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(TestBasePluginInitialization))

# +
# class TestPluginManagerInitialization(unittest.TestCase):
    
#     def setUp(self):
#         # 1) Define the schema that you want to use
#         self.schema = {
#             'screen_mode': {
#                 'type': 'str',
#                 'default': '1',
#                 'allowed': ['1', 'L', 'RGB'],
#                 'required': True
#             },
#             'resolution': {
#                 'type': 'tuple',
#                 'default': (800, 480),
#             },
#             'cache_expire': {
#                 'type': 'int',
#                 'default': 2
#             }
#         }

#         # 2) Patch load_schema so it won't try to read a real file.
#         self.load_schema_patcher = patch.object(
#             PluginManager,
#             'load_schema',
#             return_value=self.schema  # Always return self.schema
#         )
#         self.mock_load_schema = self.load_schema_patcher.start()

#         # 3) Provide an example config that uses the mock schema
#         self.config = {
#             'screen_mode': 'L',
#             'resolution': (600, 400),
#             'cache_expire': 5
#         }
        
#         self.plugin_manager = PluginManager(
#             config=self.config,
#             base_schema_file='base_schema.yaml',
#             config_path=Path('/tmp')
#         )

#     def tearDown(self):
#         # Stop patching load_schema
#         self.load_schema_patcher.stop()
    
#     def test_config_defaults_applied(self):
#         """Test defaults are applied if config is missing values."""
#         partial_config = {'screen_mode': 'RGB'}

#         # This triggers self.plugin_manager.config setter, which calls load_schema
#         self.plugin_manager.config = partial_config

#         # The schema says default for 'cache_expire' => 2, 'resolution' => (800, 480)
#         self.assertEqual(self.plugin_manager.config['cache_expire'], 2)
#         self.assertEqual(self.plugin_manager.config['resolution'], (800, 480))

#     @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
#         'screen_mode': {'type': 'str', 'default': 'L', 'allowed': ['1', 'L', 'RGB'], 'required': True},
#         'resolution': {'type': 'tuple', 'default': (1024, 600), 'required': True},
#         'cache_expire': {'type': 'int', 'default': 3}
#     }))
#     def test_valid_config_passes(self, mock_file):
#         # Overwrite config with the plugin_manager.config setter
#         self.plugin_manager.config = self.config
#         self.assertEqual(self.plugin_manager.config['screen_mode'], 'L')
#         self.assertEqual(self.plugin_manager.config['resolution'], (600, 400))
#         self.assertEqual(self.plugin_manager.config['cache_expire'], 5)


#     # ---Test Invalid Config Type ---
#     @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
#         'screen_mode': {'type': 'str', 'allowed': ['1', 'L', 'RGB'], 'required': True},
#     }))
#     def test_invalid_config_value(self, mock_file):
#         """Test invalid config value raises a validation error."""
#         invalid_config = {'screen_mode': 42}  # Should be str, not int
        
#         with self.assertRaises(ValueError):
#             self.plugin_manager.config = invalid_config

#     # ---Test Missing Required Config ---
#     @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
#         'screen_mode': {'type': 'str', 'required': True},
#         'resolution': {'type': 'tuple', 'required': True},
#     }))
#     def test_missing_required_config(self, mock_file):
#         """Ensure missing required config raises an error."""
#         incomplete_config = {'cache_expire': 10}  # Missing screen_mode, resolution
        
#         with self.assertRaises(ValueError):
#             self.plugin_manager.config = incomplete_config

#     # ---Test Config Overwrite ---
#     @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
#         'cache_expire': {'type': 'int', 'default': 2}
#     }))
#     def test_config_overwrite(self, mock_file):
#         """Ensure overwriting config triggers validation."""
#         new_config = {'screen_mode': 'L', 'cache_expire': 7}
#         self.plugin_manager.config = new_config
        
#         self.assertEqual(self.plugin_manager.config['cache_expire'], 7)

#     # ---Test Schema Loading from Cache ---
#     # @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
#     #     'cache_expire': {'type': 'int', 'default': 2}
#     # }))
#     def test_schema_loads_from_cache(self):
#         """Ensure schema is loaded from cache if available."""
#         # We can directly inject a new or different schema into _schema_cache
#         self.plugin_manager._schema_cache['base_schema.yaml'] = self.schema

#         # Re-assign config => triggers the config setter => uses the cached schema
#         self.plugin_manager.config = self.config

#         # Confirm that we still get the 'cache_expire' from self.config
#         self.assertEqual(self.plugin_manager.config['cache_expire'], 5)
    
#     def test_initialization_defaults(self):
#         """Test that PluginManager initializes with default values."""
#         manager = PluginManager()
        
#         self.assertEqual(manager.config, {})
#         self.assertIsNone(manager.plugin_path)
#         self.assertIsNone(manager.config_path)
#         self.assertEqual(manager.configured_plugins, [])
#         self.assertEqual(manager.active_plugins, [])
#         self.assertEqual(manager.dormant_plugins, [])
    
#     def test_initialization_custom(self):
#         """Test initialization with custom values."""
#         config = {'debug': True}
#         plugin_path = Path('/plugins')
#         config_path = Path('/config')
        
#         manager = PluginManager(config=config, plugin_path=plugin_path, config_path=config_path)
        
#         self.assertEqual(manager.config, config)
#         self.assertEqual(manager.plugin_path, plugin_path)
#         self.assertEqual(manager.config_path, config_path)
#         self.assertEqual(manager.configured_plugins, [])
#         self.assertEqual(manager.active_plugins, [])
#         self.assertEqual(manager.dormant_plugins, [])

#     def test_empty_lists_on_init(self):
#         """Ensure active and dormant plugins start as empty lists."""
#         manager = PluginManager()
#         self.assertIsInstance(manager.active_plugins, list)
#         self.assertIsInstance(manager.dormant_plugins, list)
#         self.assertEqual(len(manager.active_plugins), 0)
#         self.assertEqual(len(manager.dormant_plugins), 0)

#     def test_default_list_isolation(self):
#         """Test that each PluginManager instance has isolated lists."""
#         manager1 = PluginManager()
#         manager2 = PluginManager()
        
#         manager1.active_plugins.append("plugin1")
#         self.assertNotIn("plugin1", manager2.active_plugins)
    
#     def test_path_type_validation(self):
#         """Ensure plugin_path and config_path accept Path, str (converted to Path), or None."""
        
#         # Test string -> Path conversion (should not raise)
#         manager = PluginManager(plugin_path="invalid/path")
#         self.assertEqual(manager.plugin_path, Path("invalid/path"))
    
#         # Test valid Path object (should not raise)
#         manager = PluginManager(plugin_path=Path("/valid/path"))
#         self.assertEqual(manager.plugin_path, Path("/valid/path"))
    
#         # Test invalid type (integer should raise TypeError)
#         with self.assertRaises(TypeError):
#             PluginManager(config_path=123)  # Should raise
    
#         # Test None (valid case)
#         manager = PluginManager(plugin_path=None)
#         self.assertIsNone(manager.plugin_path)

#     def test_config_is_copied(self):
#         """Ensure config is copied during initialization."""
#         config = {'debug': True}
#         manager = PluginManager(config=config)
        
#         config['debug'] = False  # Modify original dict
#         self.assertTrue(manager.config['debug'])  # Should remain True

#     def test_none_config_defaults_to_empty_dict(self):
#         """Ensure None for config defaults to empty dictionary."""
#         manager = PluginManager(config=None)
#         self.assertEqual(manager.config, {})

#     # def setUp(self):
#     #     """Create a basic PluginManager instance for testing."""
#     #     self.plugin_manager = PluginManager()

#     def test_valid_paths(self):
#         """Test that valid paths are accepted."""
#         path = Path("/valid/path")
#         self.plugin_manager.plugin_path = path
#         self.plugin_manager.config_path = path
        
#         self.assertEqual(self.plugin_manager.plugin_path, path)
#         self.assertEqual(self.plugin_manager.config_path, path)

#     def test_invalid_path_type(self):
#         """Test that invalid path types raise TypeError."""
#         # with self.assertRaises(TypeError):
#         #     self.plugin_manager.plugin_path = "/invalid/string/path"
        
#         with self.assertRaises(TypeError):
#             self.plugin_manager.config_path = 12345  # Invalid type

#     def test_plugin_list_validation(self):
#         """Ensure configured_plugins accepts valid list of dictionaries."""
#         valid_plugins = [
#             {"plugin": "weather_plugin", "base_config": {}},
#             {"plugin": "news_plugin", "base_config": {}}
#         ]
#         self.plugin_manager.configured_plugins = valid_plugins
#         self.assertEqual(len(self.plugin_manager.configured_plugins), 2)

#     def test_invalid_plugin_structure(self):
#         """Ensure configured_plugins raises error for invalid structures."""
#         with self.assertRaises(TypeError):
#             self.plugin_manager.configured_plugins = "invalid_string"

#         with self.assertRaises(TypeError):
#             self.plugin_manager.configured_plugins = [123, "string"]

#         with self.assertRaises(ValueError):
#             self.plugin_manager.configured_plugins = [
#                 {"base_config": {}},  # Missing 'plugin' key
#                 {"plugin": "plugin_without_config"}  # Missing 'base_config'
#             ]

# ## these all pass in the interpreter, but don't pass here - probably something to do with the test suite

#     def test_load_schema_without_config_path(self):
#         """Test loading schema without setting config_path."""
#         self.plugin_manager.config_path = None
#         with self.assertRaises(FileNotFoundError):
#             self.plugin_manager.load_schema('base_schema.yaml')
    
#     @patch('pathlib.Path.is_file', return_value=False)
#     def test_load_schema_file_not_found(self, mock_is_file):
#         """Test loading schema when the schema file is missing."""
#         with self.assertRaises(FileNotFoundError):
#             self.plugin_manager.load_schema('missing_schema.yaml')
    
#     @patch('builtins.open', new_callable=mock_open, read_data="invalid_yaml: [unbalanced_bracket")
#     def test_load_schema_malformed_yaml(self, mock_file):
#         """Test error handling when schema contains invalid YAML."""
#         with self.assertRaises(ValueError):
#             self.plugin_manager.load_schema('malformed_schema.yaml')

# -

if __name__ == '__main__':
    unittest.main()


