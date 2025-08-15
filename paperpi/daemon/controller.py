import logging

logger = logging.getLogger(__name__)


class DaemonController:
    """
    Central controller object for the PaperPi daemon.
    Tracks runtime state, configuration, and lifecycle status.
    """

    def __init__(self):
        self.running = False
        self.config_store = {}

    def stop(self):
        """Signal the daemon to shut down."""
        logger.info("Stopping daemon...")
        self.running = False

    def set_config(self, config: dict, scope: str = 'default') -> None:
        """
        Store a configuration dictionary under a named scope.
        
        Args:
            config (dict): Configuration data to store.
            scope (str): Namespace under which to store the config.
        """
        self.config_store[scope] = config

    def get_config(self, scope: str = 'default') -> dict:
        """
        Retrieve stored configuration for a given scope.
        
        Args:
            scope (str): Namespace to retrieve config from.
        
        Returns:
            dict: The configuration dictionary (empty if not set).
        """
        return self.config_store.get(scope, {})


    def init_schema_aliases(self) -> None:
        """Initialize friendly schema aliases in the config_store.

        Aliases map human-friendly names used by /schema/<name> to concrete
        sources:
          - cache: use a cached schema under config_store['schemas'][cache_key]
          - registry: resolve via config_store['registry'][name]
        """
        aliases = self.config_store.setdefault('schema_aliases', {})

        # Application schema (token-expanded and cached during daemon startup)
        aliases['app'] = {
            'source': 'cache',
            'cache_key': 'application_effective',
        }
        aliases['application'] = {
            'source': 'cache',
            'cache_key': 'application_effective',
        }
