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
from unittest.mock import patch, mock_open
import logging
import yaml

try:
    from paperpi.library.plugin_manager import PluginManager
    from paperpi.library.exceptions import *
except ModuleNotFoundError:
    from library.plugin_manager import PluginManager
    from library.exceptions import *


class TestPluginManagerInitialization(unittest.TestCase):

    def setUp(self):
        self.schema = {
            'screen_mode': {
                'type': 'str',
                'default': '1',
                'allowed': ['1', 'L', 'RGB'],
                'required': True
            },
            'resolution': {
                'type': 'tuple',
                'default': (800, 480),
                'required': True
            },
            'cache_expire': {
                'type': 'int',
                'default': 2
            }
        }
        self.config = {
            'screen_mode': 'L',
            'resolution': (600, 400),
            'cache_expire': 5
        }

        # Simulate schema YAML
        self.mock_schema_yaml = yaml.dump(self.schema)

        # Base plugin manager initialization
        self.plugin_manager = PluginManager(
            config=self.config,
            base_schema_file='base_schema.yaml',
            config_path=Path('/tmp')
        )
    
    # ---Test Default Config ---
    def test_config_defaults_applied(self):
        """Test defaults are applied if config is missing values."""
        partial_config = {'screen_mode': 'RGB'}
        self.plugin_manager.config = partial_config
        
        self.assertEqual(self.plugin_manager.config['cache_expire'], 2)  # Default
        self.assertEqual(self.plugin_manager.config['resolution'], (800, 480))

    # ---Test Full Config Validation ---
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
        'screen_mode': {'type': 'str', 'default': 'L', 'allowed': ['1', 'L', 'RGB'], 'required': True},
        'resolution': {'type': 'tuple', 'default': (1024, 600), 'required': True},
        'cache_expire': {'type': 'int', 'default': 3}
    }))
    def test_valid_config_passes(self, mock_file):
        """Ensure valid config passes validation."""
        self.plugin_manager.config = self.config
        
        self.assertEqual(self.plugin_manager.config['screen_mode'], 'L')
        self.assertEqual(self.plugin_manager.config['resolution'], (600, 400))
        self.assertEqual(self.plugin_manager.config['cache_expire'], 5)

    # ---Test Invalid Config Type ---
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
        'screen_mode': {'type': 'str', 'allowed': ['1', 'L', 'RGB'], 'required': True},
    }))
    def test_invalid_config_value(self, mock_file):
        """Test invalid config value raises a validation error."""
        invalid_config = {'screen_mode': 42}  # Should be str, not int
        
        with self.assertRaises(ValueError):
            self.plugin_manager.config = invalid_config

    # ---Test Missing Required Config ---
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
        'screen_mode': {'type': 'str', 'required': True},
        'resolution': {'type': 'tuple', 'required': True},
    }))
    def test_missing_required_config(self, mock_file):
        """Ensure missing required config raises an error."""
        incomplete_config = {'cache_expire': 10}  # Missing screen_mode, resolution
        
        with self.assertRaises(ValueError):
            self.plugin_manager.config = incomplete_config

    # ---Test Config Overwrite ---
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
        'cache_expire': {'type': 'int', 'default': 2}
    }))
    def test_config_overwrite(self, mock_file):
        """Ensure overwriting config triggers validation."""
        new_config = {'cache_expire': 7}
        self.plugin_manager.config = new_config
        
        self.assertEqual(self.plugin_manager.config['cache_expire'], 7)

    # ---Test Schema Loading from Cache ---
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({
        'cache_expire': {'type': 'int', 'default': 2}
    }))
    def test_schema_loads_from_cache(self, mock_file):
        """Ensure schema is loaded from cache if available."""
        self.plugin_manager._schema_cache['base_schema.yaml'] = self.schema
        
        self.plugin_manager.config = self.config
        mock_file.assert_not_called()  # Schema loaded from cache, no file read
        
        self.assertEqual(self.plugin_manager.config['cache_expire'], 5)
    
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
        
        manager = PluginManager(config=config, plugin_path=plugin_path, config_path=config_path)
        
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
    
    def test_path_type_validation(self):
        """Ensure plugin_path and config_path accept Path, str (converted to Path), or None."""
        
        # Test string -> Path conversion (should not raise)
        manager = PluginManager(plugin_path="invalid/path")
        self.assertEqual(manager.plugin_path, Path("invalid/path"))
    
        # Test valid Path object (should not raise)
        manager = PluginManager(plugin_path=Path("/valid/path"))
        self.assertEqual(manager.plugin_path, Path("/valid/path"))
    
        # Test invalid type (integer should raise TypeError)
        with self.assertRaises(TypeError):
            PluginManager(config_path=123)  # Should raise
    
        # Test None (valid case)
        manager = PluginManager(plugin_path=None)
        self.assertIsNone(manager.plugin_path)

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

    def setUp(self):
        """Create a basic PluginManager instance for testing."""
        self.plugin_manager = PluginManager()

    def test_valid_paths(self):
        """Test that valid paths are accepted."""
        path = Path("/valid/path")
        self.plugin_manager.plugin_path = path
        self.plugin_manager.config_path = path
        
        self.assertEqual(self.plugin_manager.plugin_path, path)
        self.assertEqual(self.plugin_manager.config_path, path)

    def test_invalid_path_type(self):
        """Test that invalid path types raise TypeError."""
        # with self.assertRaises(TypeError):
        #     self.plugin_manager.plugin_path = "/invalid/string/path"
        
        with self.assertRaises(TypeError):
            self.plugin_manager.config_path = 12345  # Invalid type

    def test_plugin_list_validation(self):
        """Ensure configured_plugins accepts valid list of dictionaries."""
        valid_plugins = [
            {"plugin": "weather_plugin", "base_config": {}},
            {"plugin": "news_plugin", "base_config": {}}
        ]
        self.plugin_manager.configured_plugins = valid_plugins
        self.assertEqual(len(self.plugin_manager.configured_plugins), 2)

    def test_invalid_plugin_structure(self):
        """Ensure configured_plugins raises error for invalid structures."""
        with self.assertRaises(TypeError):
            self.plugin_manager.configured_plugins = "invalid_string"

        with self.assertRaises(TypeError):
            self.plugin_manager.configured_plugins = [123, "string"]

        with self.assertRaises(ValueError):
            self.plugin_manager.configured_plugins = [
                {"base_config": {}},  # Missing 'plugin' key
                {"plugin": "plugin_without_config"}  # Missing 'base_config'
            ]

    @patch("logging.Logger.error")
    def test_plugin_error_logging(self, mock_logger):
        """Ensure logger captures plugin validation errors."""
        with self.assertRaises(ValueError):
            self.plugin_manager.configured_plugins = [{"base_config": {}}]
        
        mock_logger.assert_called_with("Missing 'plugin' or 'base_config' keys in plugin.") 


unittest.main(argv=[''], verbosity=2, exit=False)

# +
# unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(TestBasePluginInitialization))
# -

if __name__ == '__main__':
    unittest.main()


