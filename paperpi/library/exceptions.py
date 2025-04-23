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

class PluginError(Exception):
    def __init__(self, message: str, plugin_name: str = "Unknown Plugin"):
        """
        General-purpose error for plugins.

        Args:
            message (str): The error message describing what went wrong.
            plugin_name (str): The name of the plugin where the error occurred.
        """
        self.plugin_name = plugin_name
        super().__init__(f"[{plugin_name}] {message}")


class ImageError(PluginError):
    """Exception raised for image processing errors."""
    def __init__(self, message: str, plugin_name: str = None):
        super().__init__(message, plugin_name)


class FileError(PluginError):
    """Exception raised for file I/O errors (e.g., saving or accessing cached files)."""
    def __init__(self, message: str, plugin_name: str = None):
        super().__init__(message, plugin_name)


class PluginTimeoutError(PluginError):
    """Exception raised when a plugin exceeds its allowed execution time."""
    def __init__(self, message: str, plugin_name: str = None):
        super().__init__(message, plugin_name)


class ConfigurationError(PluginError):
    """Exception raised when there is a fatal configuration error"""
    def __init__(self, message: str, plugin_name: str = None):
        super().__init__(message, plugin_name)
