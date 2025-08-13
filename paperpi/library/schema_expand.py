

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable


class ProviderRegistry:
    """
    Minimal registry that maps token names to zero-arg callables.

    Example:
        REGISTRY.register('DISPLAY_TYPES', get_display_types)
        value = REGISTRY.resolve('DISPLAY_TYPES')  # calls provider
    """

    def __init__(self) -> None:
        self._providers: Dict[str, Callable[[], Any]] = {}

    def register(self, name: str, fn: Callable[[], Any]) -> None:
        if not callable(fn):
            raise TypeError('provider must be callable')
        self._providers[name] = fn

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)

    def resolve(self, name: str) -> Any:
        fn = self._providers.get(name)
        if fn is None:
            return None
        return fn()


# Shared default registry instance
REGISTRY = ProviderRegistry()


def _is_token(value: Any) -> bool:
    return isinstance(value, str) and value.startswith('${') and value.endswith('}') and len(value) > 3


def _expand_token(value: Any, registry: ProviderRegistry) -> Any:
    if _is_token(value):
        token = value[2:-1]
        resolved = registry.resolve(token)
        return resolved if resolved is not None else value
    return value


def _expand_in_mapping(obj: Dict[str, Any], fields: Iterable[str], registry: ProviderRegistry) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            out[k] = _expand_in_mapping(v, fields, registry)
        elif isinstance(v, list):
            out[k] = _expand_in_sequence(v, fields, registry)
        else:
            # Only expand tokens for specific field names when inside a field-rule mapping
            out[k] = _expand_token(v, registry) if k in fields else v
    return out


def _expand_in_sequence(seq: Iterable[Any], fields: Iterable[str], registry: ProviderRegistry) -> list[Any]:
    out = []
    for item in seq:
        if isinstance(item, dict):
            out.append(_expand_in_mapping(item, fields, registry))
        elif isinstance(item, list):
            out.append(_expand_in_sequence(item, fields, registry))
        else:
            out.append(_expand_token(item, registry))
    return out


def expand_tokens_in_schema(schema: Dict[str, Any], *, fields: Iterable[str] = ('allowed', 'default'), registry: ProviderRegistry = REGISTRY) -> Dict[str, Any]:
    """
    Expand ${TOKEN} placeholders within a schema dictionary.

    By default, only the values of keys named in `fields` are expanded
    (e.g., 'allowed' and 'default'). This keeps expansion targeted to the
    rule locations and avoids changing arbitrary strings.

    Args:
        schema: Dict representing a schema section (e.g., the 'main' block).
        fields: Field names whose values may contain tokens to expand.
        registry: ProviderRegistry to resolve tokens.

    Returns:
        A new dict with tokens expanded where providers are registered. If a
        token has no provider, the original string is kept as-is.
    """
    if not isinstance(schema, dict):
        return schema

    # The schema is typically a mapping of field_name -> rules
    expanded: Dict[str, Any] = {}
    for field_name, rules in schema.items():
        if isinstance(rules, dict):
            expanded[field_name] = _expand_in_mapping(rules, fields, registry)
        elif isinstance(rules, list):
            expanded[field_name] = _expand_in_sequence(rules, fields, registry)
        else:
            expanded[field_name] = rules
    return expanded