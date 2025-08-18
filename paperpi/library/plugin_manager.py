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
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, field
import importlib.util
from types import ModuleType
from pathlib import Path
from time import monotonic



try:
    from paperpi.library.config_utils import check_config_problems
    from paperpi.library.base_plugin import BasePlugin
except ImportError:
#     # support jupyter developement
    from config_utils import check_config_problems
    from base_plugin import BasePlugin




logger = logging.getLogger(__name__)


# -

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
        "last_image_hash": None,
        "last_write_ts": 0.0
    })
    obj: Optional["BasePlugin"] = None  


@dataclass
class TickResult:
    needs_write: bool = False
    fg_uuid: Optional[str] = None
    reason: Optional[str] = None
    image: Optional[Any] = None
    image_hash: Optional[str] = None


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

        self._fg_index: int = 0

    def _foreground(self):
        """
        Return the current foreground PluginRecord, if any.
        """
        if not self.active_plugins:
            return None
        idx = max(0, min(self._fg_index, len(self.active_plugins) - 1))
        return self.active_plugins[idx]

    def _advance_rotation(self):
        """
        Advance to the next active plugin (round-robin).
        """
        if self.active_plugins:
            self._fg_index = (self._fg_index + 1) % len(self.active_plugins)
    
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

    def _load_module_from_file(self, file_path: Path, module_name: str) -> ModuleType:
        """Load a Python module from an arbitrary file path."""
        if not file_path.exists():
            raise FileNotFoundError(f"Module file not found: {file_path}")
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not create spec for {file_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        return mod
    
    def _load_attr(self, mod: ModuleType, attr_name: str):
        """Get an attribute from a module with a clear error if missing."""
        if not hasattr(mod, attr_name):
            raise AttributeError(f"Module '{mod.__name__}' has no attribute '{attr_name}'")
        return getattr(mod, attr_name)

        
    def _load_plugin_class_from_path(self, plugin_type: str):
        plugin_file = (self._plugin_path / plugin_type / "plugin.py").resolve()
        mod = self._load_module_from_file(plugin_file, f"paperpi_plugin_{plugin_type}")
        return self._load_attr(mod, "Plugin")

    def _layout_file_for(self, plugin_type: str) -> Path:
        """Return {plugin_path}/{plugin_type}/layout.py"""
        return (self._plugin_path / plugin_type / "layout.py").resolve()

    def _extract_layout_name(self, cfg: Dict[str, Any]) -> Optional[str]:
        """
        Prefer cfg['layout']['name'] if 'layout' is a dict; else cfg.get('layout_name').
        """
        layout = cfg.get("layout")
        if isinstance(layout, dict) and "name" in layout:
            return layout.get("name")
        return cfg.get("layout_name")

    def _load_layout_dict_from_path(self, plugin_type: str, layout_name: str) -> Dict[str, Any]:
        """
        Load a layout dictionary named `layout_name` from {plugin_path}/{plugin_type}/layout.py.
        Expects the named attribute in the module to be a dict.
        """
        layout_file = self._layout_file_for(plugin_type)
        mod = self._load_module_from_file(layout_file, f"paperpi_layout_{plugin_type}")
        layout = getattr(mod, layout_name, None)
        if layout is None:
            raise AttributeError(f"{layout_file} has no layout dict named '{layout_name}'")
        if not isinstance(layout, dict):
            raise TypeError(f"{layout_file}:{layout_name} is not a dict (got {type(layout).__name__})")
        return layout

    def _safe_plugin_update(self, rec, force: bool = False) -> bool:
        """
        Safely call rec.obj.update(); manage failure counters and timestamps

        Returns True on succes, False on failures/exception
        """
        obj = getattr(rec, "obj", None)
        # fail fast
        if not obj:
            return False

        try:
            ok = obj.update(force=force)
        except Exception as e:
            self.logger.error(f"Update exception | {rec.plugin}: {e}")
            rec.status['consecutive_failures'] = rec.status.get('consecutive_failures', 0) + 1

        if not isinstance(ok, bool):
            # be strict; treat non-bool as a failure
            self.logger.warning(f'Plugin {rec.plugin} returned non-bool value: {ok}')
            ok = False

        if ok:
            # zero out consecutive failures
            rec.status['consecutive_failures'] = 0
            rec.status['last_update_ts'] = monotonic()
            # track high_priority state
            rec.status["high_priority"] = bool(getattr(obj, "high_priority", False))
            return True

        # failure
        rec.status["consecutive_failures"] = rec.status.get("consecutive_failures", 0) + 1
        return False
    
    # --- Public, simple wrappers for loaders (used by smoke tests & callers) ---
    def load_plugin_class(self, plugin_name: str):
        """Public wrapper: load class 'Plugin' from {plugin_path}/{plugin_name}/plugin.py."""
        return self._load_plugin_class_from_path(plugin_name)

    def load_layout_dict(self, plugin_name: str, layout_name: str) -> Dict[str, Any]:
        """Public wrapper: load a layout dict named `layout_name` from {plugin_path}/{plugin_name}/layout.py."""
        return self._load_layout_dict_from_path(plugin_name, layout_name)
    
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

                    PluginClass = self._load_plugin_class_from_path(rec.plugin)

                    # determine layout name from config (supports {'layout': {'name': ...}} or 'layout_name')
                    layout_name = self._extract_layout_name(rec.plugin_config)
                    layout_dict = None
                    if layout_name:
                        try:
                            layout_dict = self._load_layout_dict_from_path(rec.plugin, layout_name)
                            self.logger.debug("Loaded layout '%s' for %s", layout_name, module_name)
                        except Exception as le:
                            # If a layout is specified but cannot be loaded, treat as build error
                            raise RuntimeError(f"Failed to load layout '{layout_name}' for {module_name}: {le}") from le

                    # build the plugin (pass layout if supported, else attach after)
                    try:
                        rec.obj = PluginClass(
                            name=plugin_name,
                            uuid=rec.uuid,
                            plugin_config=rec.plugin_config,
                            plugin_params=rec.plugin_params,
                            layout=layout_dict
                        )
                    except TypeError:
                        rec.obj = PluginClass(
                            name=plugin_name,
                            uuid=rec.uuid,
                            plugin_config=rec.plugin_config,
                            plugin_params=rec.plugin_params
                        )
                        if layout_dict is not None:
                            # attach via common attribute names if constructor doesn't accept 'layout'
                            if hasattr(rec.obj, "layout"):
                                setattr(rec.obj, "layout", layout_dict)
                            elif hasattr(rec.obj, "epd_layout"):
                                setattr(rec.obj, "epd_layout", layout_dict)
                            else:
                                # last-resort stash
                                setattr(rec.obj, "_layout_dict", layout_dict)

                    
                    # classify: dormant plugins are saved to the appropriate list
                    is_dormant = bool(getattr(rec.obj, 'dormant', False)) or rec.status.get('dormant')
                    rec.status['dormant'] = is_dormant
                    if is_dormant:
                        self.dormant_plugins.append(rec)
                    else:
                        self.active_plugins.append(rec)
                except Exception as e:
                    self.logger.error(f'Failed to build plugin {rec.plugin}: {e}')
                    rec.status['disabled'] = True
                    self.disabled_plugins.append(rec)
            else:
                rec.status['disabled'] = True
                self.disabled_plugins.append(rec)

        self.logger.info(
            f'Plugin build complete: {len(self.active_plugins)} active | {len(self.dormant_plugins)} dormant | {len(self.disabled_plugins)} disabled'
        )
        



# +
import sys
import pathlib
import logging

# 1) Make the repo importable
PROJECT_ROOT = pathlib.Path.home() / 'src' / 'PaperPi-Web'
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 2) Reset and configure logging for Jupyter
# force=True reconfigures even if another handler is already attached
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

# 3) Set levels for your package/module loggers
# Adjust names to match where your class logs from.
for name in [
    'paperpi',                         # whole package
    'paperpi.plugins',                 # subpackage
    'paperpi.plugins.plugin_manager',  # module with the class, if applicable
    'PluginManager',                   # if someone used this bare name
]:
    logging.getLogger(name).setLevel(logging.DEBUG)

# Optional: show effective config for a target logger
lg = logging.getLogger('paperpi.plugins.plugin_manager')
print('effective level:', logging.getLevelName(lg.getEffectiveLevel()))
print('handlers:', lg.handlers or logging.getLogger().handlers)

# +
p = PluginManager(plugin_path='/home/pi/src/PaperPi-Web/paperpi/plugins/')
p.load_from_daemon()
p.plugin_path

vc = p.validate_config()

p.build_plugins(vc)
# -


p.active_plugins

p.dormant_plugins

fg = p._foreground()
print("FG#1", fg.plugin, fg.plugin_config.get("name"), fg.uuid)
fg.obj.update()
fg.obj.image

p._advance_rotation()
print("FG#2", p._foreground().plugin)
p._foreground().obj.update()
p._foreground().obj.image

p._advance_rotation()
print("FG#3", p._foreground().plugin)
p._foreground().obj.update()
p._foreground().obj.image

# +
p.records[1].obj.update()

p.records[1].obj.image_hash
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
