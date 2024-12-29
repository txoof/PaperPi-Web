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
import unittest
from pathlib import Path
import shutil
from PIL import Image
import os
import time
from unittest.mock import patch, MagicMock
import signal

import requests
# -

try:
    from paperpi.library.base_plugin import BasePlugin
    from paperpi.library.exceptions import *
    from paperpi.library.base_plugin import logger
except ModuleNotFoundError:
    from library.base_plugin import BasePlugin
    from library.exceptions import *
    from library.base_plugin import logger


class TestBasePluginInitialization(unittest.TestCase):

    def setUp(self):
        """Set up a temporary cache directory for testing."""
        self.temp_cache_root = Path('/tmp/test_plugin_cache/')
        self.temp_cache_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up by removing the test cache directory after each test."""
        if self.temp_cache_root.exists():
            shutil.rmtree(self.temp_cache_root)

    # Test default initialization
    def test_default_initialization(self):
        plugin = BasePlugin()
        self.assertEqual(plugin.name, "Unset")
        self.assertEqual(plugin.resolution, (800, 480))
        self.assertEqual(plugin.screen_mode, '1')
        self.assertTrue(plugin.uuid.startswith('self_set-'))
        self.assertFalse(plugin.dormant)
        self.assertEqual(plugin.refresh_interval, 30)
        self.assertEqual(plugin.cache_root, Path('/tmp/BasePlugin_cache/'))

    # Test custom initialization
    def test_custom_initialization(self):
        plugin = BasePlugin(
            name="WeatherPlugin",
            uuid="custom-uuid-1234",
            duration=120,
            resolution=(1024, 600),
            screen_mode='RGB',
            refresh_interval=60,
            cache_root=self.temp_cache_root
        )
        self.assertEqual(plugin.name, "WeatherPlugin")
        self.assertEqual(plugin.uuid, "custom-uuid-1234")
        self.assertEqual(plugin.duration, 120)
        self.assertEqual(plugin.resolution, (1024, 600))
        self.assertEqual(plugin.screen_mode, 'RGB')
        self.assertEqual(plugin.refresh_interval, 60)
        self.assertEqual(plugin.cache_root, self.temp_cache_root)

    # Test UUID auto-generation when not provided
    def test_uuid_auto_generation(self):
        plugin = BasePlugin(name="TestPlugin")
        self.assertTrue(plugin.uuid.startswith('self_set-'))
        self.assertEqual(plugin.name, "TestPlugin")

    # Test invalid resolution (non-tuple or incorrect length)
    def test_invalid_resolution(self):
        with self.assertRaises(ValueError):
            BasePlugin(resolution=(1024,))  # Only one value

        with self.assertRaises(TypeError):
            BasePlugin(resolution="1024x600")  # Wrong type (str instead of tuple)

        with self.assertRaises(ValueError):
            BasePlugin(resolution=(0, 480))  # Zero width
    
        with self.assertRaises(ValueError):
            BasePlugin(resolution=(-800, 480))  # Negative width
    
    
    # Test cache directory creation
    def test_cache_directory_creation(self):
        plugin = BasePlugin(cache_root=self.temp_cache_root)
        self.assertTrue(plugin.cache_root.exists())

        # Check if cache_dir is correctly initialized
        self.assertEqual(plugin.cache_dir, self.temp_cache_root / "Unset")

    # Test invalid cache expiration
    def test_invalid_cache_expiration(self):
        with self.assertRaises(ValueError):
            BasePlugin(cache_expire=-5)  # Negative expiration
            
        with self.assertRaises(TypeError):
            BasePlugin(cache_expire="invalid") # string instead of float/int

    # Test force_onebit property
    def test_force_onebit(self):
        plugin = BasePlugin(force_onebit=True)
        self.assertTrue(plugin.force_onebit)

        plugin.force_onebit = False
        self.assertFalse(plugin.force_onebit)

    # Test screen_mode validation
    def test_invalid_screen_mode(self):
        with self.assertRaises(ValueError):
            BasePlugin(screen_mode='XYZ')  # Invalid mode
            
        for mode in ['L', '1', 'RGB']:
            plugin = BasePlugin(screen_mode=mode)
            self.assertEqual(plugin.screen_mode, mode)
            
        with self.assertRaises(TypeError):
            BasePlugin(screen_mode=1)  # invalid type            

    # test dormant works as expected
    def test_dormant_property(self):
        plugin = BasePlugin(dormant=True)
        self.assertTrue(plugin.dormant)
    
        plugin.dormant = False
        self.assertFalse(plugin.dormant)
    
        with self.assertRaises(ValueError):
            plugin.dormant = "invalid"  # Non-boolean value
            
    def test_image_hash(self):
        plugin = BasePlugin()
        plugin.image = Image.new("RGB", (10, 10), "white")  # PIL image
        hash_before = plugin.image_hash
        self.assertTrue(hash_before)
    
        # Modify the image and check for a new hash
        plugin.image = Image.new("RGB", (10, 10), "black")
        self.assertNotEqual(hash_before, plugin.image_hash)

        plugin.image = None
        self.assertEqual(plugin.image_hash, "")  # Empty when image is removed

    def test_high_priority(self):
        plugin = BasePlugin()
        self.assertFalse(plugin.high_priority)
    
        plugin.high_priority = True
        self.assertTrue(plugin.high_priority)
    
        with self.assertRaises(ValueError):
            plugin.high_priority = "invalid"  # Non-boolean value

    def test_cache_root_reset_to_default(self):
        plugin = BasePlugin(cache_root=None)
        self.assertEqual(plugin.cache_root, Path('/tmp/BasePlugin_cache/'))

    def test_cache_dir_defaults_to_cache_root(self):
        plugin = BasePlugin(name="TestPlugin", cache_root=self.temp_cache_root)
        self.assertEqual(plugin.cache_dir, self.temp_cache_root / "TestPlugin")
    
        plugin.cache_dir = None
        self.assertEqual(plugin.cache_dir, self.temp_cache_root / "TestPlugin")

    def test_layout_conversion_rgb_support(self):
        layout = {
            'block1': {
                'type': 'ImageBlock',
                'abs_coordinates': (0, 0),
                'rgb_support': True
            },
            'block2': {
                'type': 'TextBlock',
                'font': '../fonts/Anton/Anton-Regular.ttf',
                'abs_coordinates': (0, None),
                'relative': ['block2', 'block1'],
                'rgb_support': False
            }
        }
        plugin = BasePlugin(screen_mode='RGB', layout=layout)
        
        # Only blocks with rgb_support=True should be converted
        self.assertEqual(plugin.layout['block1']['mode'], 'RGB')
        self.assertNotIn('mode', plugin.layout['block2'])  # No mode added for block2

    def test_clear_cache(self):
        plugin = BasePlugin(name="TestPlugin", cache_root=self.temp_cache_root)
        cache_file = plugin.cache_dir / "TestPlugin_image.png"
        cache_file.touch()
    
        # Modify the timestamp to simulate expiration
        expired_time = int(time.time() - (plugin.cache_expire + 1) * 86400)
        os.utime(cache_file, (expired_time, expired_time))    

        # Clear expired files
        plugin.clear_cache()
        self.assertFalse(cache_file.exists())  # File should be deleted
    
        # Touch again to reset and test non-expired case
        cache_file.touch()
        plugin.clear_cache(all_files=False)
        self.assertTrue(cache_file.exists())  # File should remain

    @patch("requests.get")
    def test_download_image(self, mock_get):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b'test_data']
        mock_response.raise_for_status = lambda: None
        mock_get.return_value = mock_response
    
        plugin = BasePlugin(name="TestPlugin", cache_root=self.temp_cache_root)
        url = "http://example.com/image.png"
        downloaded_path = plugin.download_image(url)
    
        self.assertTrue(downloaded_path.exists())  # Image should be cached

    def test_timeout_handler(self):
        plugin = BasePlugin(name="TestPlugin")
        with self.assertRaises(PluginTimeoutError):
            plugin.timeout_handler(signal.SIGALRM, None)

# +
# unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(TestBasePluginInitialization))
# -

if __name__ == '__main__':
    unittest.main()


