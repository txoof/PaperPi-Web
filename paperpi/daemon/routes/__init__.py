import importlib
import pkgutil

ROUTE_REGISTRY = {}

# Dynamically discover and import all modules in this package
for _, module_name, _ in pkgutil.iter_modules(__path__):
    module = importlib.import_module(f'{__name__}.{module_name}')
    routes = getattr(module, 'ROUTES', None)
    if isinstance(routes, dict):
        ROUTE_REGISTRY.update(routes)