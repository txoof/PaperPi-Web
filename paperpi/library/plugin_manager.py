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
import uuid
import importlib
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, field



try:
    from paperpi.library.config_utils import check_config_problems
    from paperpi.library.base_plugin import BasePlugin
except ImportError:
#     # support jupyter developement
    from config_utils import check_config_problems
    from base_plugin import BasePlugin




logger = logging.getLogger(__name__)


# +
@dataclass
class PluginRecord:
    uuid: str
    plugin: str
    plugin_config: Dict[str, Any]
    plugin_params: Dict[str, Any]
    raw: Dict[str, Any] = field(default_factory=dict)   # optional
    validation: Dict[str, Any] = field(default_factory=lambda: {"ok": False, "problems": {}})
    status: Dict[str, Any] = field(default_factory=lambda: {
        "disabled": False,
        "consecutive_failures": 0,
        "dormant": False,
        "high_priority": False,
        "last_update_ts": 0.0,
    })
    obj: Optional["BasePlugin"] = None  



# +
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
        cache_expire: int = 2,
        daemon_url: str | None = None,
        daemon_port: int = 2822,
        plugin_path: str = None
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
        self.daemon_port = daemon_port
        self.daemon_url = daemon_url or f"http://localhost:{daemon_port}"
        self.plugin_path = plugin_path
        self.records: List[PluginRecord] = [] # master list of plugins in memory

        # Prepare data structures
        self.configured_plugins: List[Dict[str, Any]] = [] # all plugin configurations provided by daemon
        self.active_plugins: List[Dict[str, Any]] = [] 
        self.dormant_plugins: List[Dict[str, Any]] = []        
        self.disabled_plugins: List[Dict[str, Any]] = [] # all plugins that are disabled due to failures or bad config

        # keys to be dropped when comparing plugin configs
        # self._transient_config_keys = ['uuid', 'plugin_status']
        self.load_from_daemon()

    def _new_uuid(self) -> str:
        return str(uuid.uuid4())

    def _make_record_from_entry(self, entry: Dict[str, Any]) -> PluginRecord:
        # keep the raw data from the daemon
        raw = dict(entry)
        plugin = entry.get("plugin")
        cfg = entry.get("plugin_config", {})
        params = entry.get("plugin_params", {})

        # carry uuid forward if provided
        uid = entry.get("uuid") or self._new_uuid()

        return PluginRecord(
            uuid=uid,
            plugin=plugin,
            plugin_config=cfg,
            plugin_params=params,
            raw=raw,
        )


    def _load_plugin_class_from_path(self, plugin_type: str):
        plugin_file = (self._plugin_path / plugin_type / "plugin.py").resolve()
        if not plugin_file or not plugin_file.exists():
            raise FileNotFoundError(f'Plugin module not found for {plugin_type}: {plugin_file}')

        module_name = f'paperpi_plugin_{plugin_type}'
        spec = importlib.util.spec_from_file_location(module_name, str(plugin_file))
        if spec is None or spec.loader is None:
            raise ImportError(f'Could not load spec for {plugin_file}')

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if not hasattr(mod, "Plugin"):
            raise AttributeError(f'{plugin_file} does not define a class named "Plugin"')
        return getattr(mod, "Plugin")
    
    @property
    def plugin_path(self):
        return self._plugin_path

    @plugin_path.setter
    def plugin_path(self, path):
        if not path:
            self._plugin_path = Path('')
        else:
            self._plugin_path = Path(path)
            if not self._plugin_path.exists():
                self.logger.warning('plugin_path does not appear to exist!')
        self.logger.debug(f'using plugin_path: {self._plugin_path}')

    def load_from_daemon(self) -> List[Dict[str, Any]]:
        url = f'{self.daemon_url}/config/configured_plugins'
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch configured plugins: {e}")
            self.configured_plugins = []
            return []

        try:
            payload = resp.json()
        except ValueError:
            self.logger.error('Daemon returned non-JSON response')
            self.configured_plugins = []
            return []
            
        data = payload.get("data", [])
        if not isinstance(data, list):
            self.logger.error("Invalid plugin configuration format provided by daemon")
            self.logger.debug(f"data:\n{data}")
            self.configured_plugins = []
            return []

        bad = [i for i in data if not isinstance(i, dict) or "plugin" not in i]
        if bad:
            self.logger.warning("Some plugin entries are malformed (will keep them for visibility): %d", len(bad))
    
        
        

        self.records = [self._make_record_from_entry(e) for e in data]
        self.configured_plugins = data
        self.logger.info("Loaded %d configured plugins from daemon", len(self.configured_plugins))
        return data
        

    def validate_config(self):
        """
        Validate each configured plugin using daemon-provided schemas.     
        
        - Validates `plugin_config` against the plugin base schema.
        - Validates `plugin_params` against the per-plugin schema at /schema/plugin/<type> (if present).
        - Returns a list of results: [{plugin, ok, problems:{plugin_config, plugin_params}}]
        """
        unnamed_count = 0
        base_url = self.daemon_url

        # Fetch base plugin schema once
        base_schema = {}
        self.logger.info(f'Validating {len(self.configured_plugins)} plugins')
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
        for rec in self.records:
            plugin_type = rec.plugin
            cfg = rec.plugin_config or {}
            params = rec.plugin_params or {}
            name = cfg.get('name', '')

            problems = {}
            
            if not name:
                name = f'{plugin_type}-{unnamed_count:03}'
                unnamed_count += 1

            self.logger.debug(f'Validating {plugin_type}: {name}')
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
                    self.logger.error("Validation error (plugin_params) for '%s': %s", plugin_type, e)
                    problems['plugin_params'] = {'_error': f'validation_exception: {e}'}

            ok = not problems
            rec.validation = {
                'ok': ok,
                'problems': problems
            }

            if not ok:
                rec.status['disabled'] = True
            
            results.append({
                'uuid': rec.uuid,
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

    def build_plugins(self, validated: List[Dict[str, Any]]) -> None:
        """
        Build plugin instances based on validation results.
    
        - Valid configs → instantiate plugin class, add to active_plugins.
        - Invalid configs → mark disabled, keep for UI visibility.
        - Preserves configuration order.
        """

        self.active_plugins.clear()
        self.disabled_plugins.clear()

        self.logger.debug(f'using plugin path: {self.plugin_path}')

        for rec in self.records:
            if rec.validation.get("ok"):
                try:
                    # dynamically import the plugin class
                    # Convention: plugins live in self.plugin_path / <plugin_name>.py
                    # And class is capitalized, e.g. WordClock for "word_clock"
                    module_name = rec.plugin
                    plugin_name = rec.plugin_config.get('name', None)
                    class_name = ''.join(part.capitalize() for part in module_name.split('_'))
                    self.logger.debug(f'Loading plugin class: {class_name} from {module_name}')

                    # # import dynamically
                    # mod = __import__(f'{self.plugin_path}.{module_name}', fromlist=[class_name])
                    # cls = getattr(mod, class_name)

                    PluginClass = self._load_plugin_class_from_path(rec.plugin)
                    

                    # build the plugin
                    rec.obj = PluginClass(
                        name = plugin_name,
                        uuid = rec.uuid,
                        plugin_config = rec.plugin_config,
                        plugin_params = rec.plugin_params
                    )
                    self.active_plugins.append(rec)
                except Exception as e:
                    self.logger.error(f'Failed to build plugin {rec.plugin}: {e}')
                    rec.status['disabled'] = True
                    self.disabled_plugins.append(rec)
            else:
                rec.status['disabled'] = True
                self.disabled_plugins.append(rec)

        self.logger.info(
            f'Plugin build complete: {len(self.active_plugins)} active | {len(self.disabled_plugins)} disabled'
        )
        



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

# +
p = PluginManager(plugin_path='/home/pi/src/PaperPi-Web/paperpi/plugins/')
p.load_from_daemon()
p.plugin_path

vc = p.validate_config()

p.build_plugins(vc)

p.records[0].obj.update_data()

# -

p.records[0].obj.update(force=True)

p.records[0]

plugin = p._load_plugin_class_from_path('word_clock')

# +

PluginClass = p._load_plugin_class_from_path("word_clock")
print(PluginClass)             # should print <class '...Plugin'>
inst = PluginClass(plugin_config={}, plugin_params={})
print(type(inst).__name__)     # Plugin
# -

inst.update()

print(spec)
