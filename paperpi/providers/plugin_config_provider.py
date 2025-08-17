# paperpi/library/providers/plugin_config_provider.py
from typing import Any
import requests

class PluginConfigProvider:
    """
    Provides plugin configuration and schema data from the PaperPi daemon.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get_plugin_configs(self) -> list[dict[str, Any]]:
        """
        Retrieve the full list of configured plugins from the daemon.
        """
        r = requests.get(f"{self.base_url}/config/plugins", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get("data", [])

    def get_plugin_schema(self, plugin_name: str) -> dict[str, Any]:
        """
        Retrieve the schema for a specific plugin by name.
        """
        r = requests.get(f"{self.base_url}/schema/plugins/{plugin_name}", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get("data", {})

    def get_base_plugin_schema(self) -> dict[str, Any]:
        """
        Retrieve the base plugin schema (common to all plugins).
        """
        r = requests.get(f"{self.base_url}/schema/plugin_base", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get("data", {})