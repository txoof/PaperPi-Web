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

# Enable automatic module reloading during development
# %load_ext autoreload
# %autoreload 2

# +
import logging
from pathlib import Path
import requests

from typing import Optional, Dict, List



try:
    from paperpi.library.config_utils import check_config_problems
except ImportError:
#     # support jupyter developement
    from config_utils import check_config_problems


logger = logging.getLogger(__name__)
# -

help(check_config_problems)


class PluginManager():
    """
    Manages the loading, configuration, activation, and lifecycle of plugins.

    Supports plugin schema validation, plugin instantiation, update cycles,
    foreground switching, and caching of schema files.
    """

    def __init__(
        self,
        screen_mode: str = '1',
        resolution: tuple = (800, 480),
        cache_root: str = '/tmp/PaperPi_cache/',
        max_plugin_failures: int = 5,
        cache_expire: int = 2
    ):
        """
        Initialize the PluginManager with configuration parameters.
        Parameters have defaults matching plugin_manager_schema.yaml.
        """
        self.logger = logger.getChild("PluginManager")
        self.screen_mode = screen_mode
        self.resolution = resolution
        self.cache_root = cache_root
        self.max_plugin_failures = max_plugin_failures
        self.cache_expire = cache_expire
        self._daemon_port = 2822

        # Prepare data structures
        self.configured_plugins: List[dict] = []
        self.active_plugins: List[dict] = []
        self.dormant_plugins: List[dict] = []        

        # keys to be dropped when comparing plugin configs
        # self._transient_config_keys = ['uuid', 'plugin_status']
        self.load_configured_plugins(f"http://localhost:{self._daemon_port}")

    def load_configured_plugins(self, daemon_url: str):
        url = f"{daemon_url}/config/configured_plugins"
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch configured plugins: {e}")
            self.configured_plugins = []
            return

        data = resp.json().get("data", [])
        if not isinstance(data, list):
            self.logger.error("Invalid plugin configuration format provided by daemon")
            self.logger.debug(f"data:\n{data}")
            self.configured_plugins = []

        self.configured_plugins = data
        self.logger.debug(self.configured_plugins)
        self.logger.info(f"Loaded {len(self.configured_plugins)} configured plugins from daemon")
        

    def validate_config(self):
        """
        Validate each configured plugin using daemon-provided schemas.     
        
        - Validates `plugin_config` against the plugin base schema.
        - Validates `plugin_params` against the per-plugin schema at /schema/plugin/<type> (if present).
        - Returns a list of results: [{plugin, ok, problems:{plugin_config, plugin_params}}]
        """
        unnamed_count = 0
        base_url = f"http://localhost:{self._daemon_port}"

        # Fetch base plugin schema once
        base_schema = {}
        try:
            resp = requests.get(f"{base_url}/schema/plugin_base", timeout=5)
            if resp.status_code == 200:
                payload = resp.json().get('data', {})
                # Prefer the real rules map under 'schema'; fallback to 'plugin_config'
                if isinstance(payload, dict) and isinstance(payload.get('schema'), dict):
                    base_schema = payload['schema']
                elif isinstance(payload, dict) and isinstance(payload.get('plugin_config'), dict):
                    base_schema = payload['plugin_config']
                else:
                    base_schema = {}
            else:
                self.logger.warning("/schema/plugin_base returned %s", resp.status_code)
        except Exception as e:
            self.logger.error("Failed to fetch base plugin schema: %s", e, exc_info=True)

        self.logger.debug(f'base_schema:\n{base_schema}')
        
        results = []
        for entry in (self.configured_plugins or []):
            plugin_type = entry.get('plugin')
            cfg = entry.get('plugin_config', {}) or {}
            name = cfg.get('name', '')
            if not name:
                name = f'{plugin_type}-{unnamed_count:03}'
                unnamed_count += 1
            params = entry.get('plugin_params', {}) or {}

            problems = {}

            # Validate plugin_config against base schema if available
            if isinstance(base_schema, dict) and base_schema:
                try:
                    p_cfg = check_config_problems(cfg, base_schema, strict=True)
                    if p_cfg:
                        problems['plugin_config'] = p_cfg
                except Exception as e:
                    self.logger.error("Validation error (plugin_config) for '%s': %s", plugin_type, e, exc_info=True)
                    problems['plugin_config'] = {'_error': f'validation_exception: {e}'}

            # Fetch per-plugin params schema and validate
            params_schema = {}
            if plugin_type:
                try:
                    r = requests.get(f"{base_url}/schema/plugin/{plugin_type}", timeout=5)
                    if r.status_code == 200:
                        data = r.json().get('data', {})
                        # handler may wrap under {'schema': {...}}
                        if isinstance(data, dict) and 'schema' in data and isinstance(data['schema'], dict):
                            params_schema = data['schema']
                        else:
                            params_schema = data if isinstance(data, dict) else {}
                    elif r.status_code == 404:
                        # No schema for this plugin type; treat as no constraints
                        params_schema = {}
                    else:
                        self.logger.warning("/schema/plugin/%s returned %s", plugin_type, r.status_code)
                except Exception as e:
                    self.logger.error("Failed to fetch params schema for '%s': %s", plugin_type, e, exc_info=True)

            if isinstance(params_schema, dict) and params_schema:
                try:
                    p_params = check_config_problems(params, params_schema, strict=False)
                    if p_params:
                        problems['plugin_params'] = p_params
                except Exception as e:
                    self.logger.error("Validation error (plugin_params) for '%s': %s", plugin_type, e, exc_info=True)
                    problems['plugin_params'] = {'_error': f'validation_exception: {e}'}

            ok = not problems
            results.append({
                'name': name,
                'plugin': plugin_type,
                'ok': ok,
                'problems': problems,
            })

        # Summary log
        total = len(results)
        oks = sum(1 for r in results if r['ok'])
        self.logger.info("Plugin validation: %d total | %d ok | %d with problems", total, oks, total - oks)
        return results


# +
import sys

# Configure root logger to output to stdout
logging.basicConfig(
    level=logging.DEBUG,  # or INFO
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Optional: narrow to your module logger
logging.getLogger("PluginManager").setLevel(logging.DEBUG)
# -

p = PluginManager()

p.configured_plugins

# p.load_configured_plugins("http://localhost:2822")
r = p.validate_config()

r

base = {'schema': {'name': {'type': 'str', 'default': None, 'description': 'Human readable plugin identifier'}, 'duration': {'type': 'int', 'default': 120, 'description': 'Amount of time in seconds to display plugin'}, 'refresh_interval': {'type': 'int', 'default': 60, 'description': 'Amount of time in seconds between refreshing the data for this plugin'}, 'layout_name': {'type': 'str', 'default': 'layout', 'required': True, 'description': 'Layout to use for displaying plugin'}, 'cache_dir': {'type': '(str, None)', 'default': None, 'description': 'Location within the cache to store cached content for this plugin'}, 'force_onebit': {'type': 'bool', 'default': False}, 'screen_mode': {'type': 'str', 'default': 'L', 'allowed': ['1', 'L', 'RGB']}, 'dormant': {'type': 'bool', 'default': False, 'description': 'Dormant plugins only display when required (e.g. when Spotify is actively playing)'}}}
config = {'plugin': 'word_clock',
  'plugin_config': {'name': 'Word Clock 02',
   'duration': 20,
   'refresh_interval': 60,
   'layout_name': 'layout'},
  'plugin_params': {'foo': 'bar', 'spam': 7, 'username': 'Monty'}}



params

b_schema = base['schema']
p_config = config['plugin_config']
p_config['duration'] = 'cat'


check_config_problems(p_config, b_schema)


