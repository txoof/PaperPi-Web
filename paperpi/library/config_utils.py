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

import yaml
from pathlib import Path
import logging
import shutil
import collections.abc
from typing import Any, Dict, Tuple

from epdlib.Screen import list_compatible_modules

logger = logging.getLogger(__name__)

def deep_merge(a, b):
    """
    Recursively merge dictionary `b` into dictionary `a`.

    If both `a` and `b` contain a key with a dictionary as its value,
    those dictionaries are merged recursively. Otherwise, the value from `b`
    overrides the value in `a`.

    Args:
        a (dict): The base dictionary.
        b (dict): The dictionary whose values should be merged into `a`.

    Returns:
        dict: A new dictionary containing the merged keys and values.
    """
    result = a.copy()
    for k, v in b.items():
        if (k in result and isinstance(result[k], dict)
                and isinstance(v, collections.abc.Mapping)):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def check_config_problems(config: dict, schema: dict, strict: bool = True) -> dict:
    """
    Check `config` against a dict-based schema, returning a dictionary of problems.
    Args:
        config (dict): The configuration to check.
        schema (dict): Schema describing expected keys, types, allowed values, and ranges.
        strict (bool): If True, report unknown keys not in the schema.

    Returns:
        dict: A dictionary describing problems found, including machine and human readable information.
    """
    problems = {}

    for key, rules in schema.items():
        default_val = rules.get('default')
        required = rules.get('required', False)
        allowed = rules.get('allowed')
        value_range = rules.get('range', None)
        description = rules.get('description', 'No description provided')

        try:
            expected_type = eval(rules.get('type', 'str'))
        except NameError:
            expected_type = str

        if key not in config:
            if required:
                problems[key] = {
                    "error": "missing_required",
                    "expected": expected_type.__name__,
                    "suggested_default": default_val,
                    "message": f"'{key}' is required, but missing. Suggested default: {default_val}. {description}"
                }
            continue

        value = config[key]

        if not isinstance(value, expected_type):
            problems[key] = {
                "error": "type_mismatch",
                "expected": expected_type.__name__,
                "actual": type(value).__name__,
                "suggested_default": default_val,
                "message": f"'{key}' must be of type {expected_type.__name__}, got {type(value).__name__}."
            }
            continue

        if allowed and value not in allowed:
            problems[key] = {
                "error": "invalid_value",
                "allowed": allowed,
                "actual": value,
                "suggested_default": default_val,
                "message": f"'{key}' must be one of {allowed}, got {value}."
            }
            continue

        if value_range and isinstance(value, (int, float)):
            min_val, max_val = value_range
            if not (min_val <= value <= max_val):
                problems[key] = {
                    "error": "out_of_range",
                    "range": value_range,
                    "actual": value,
                    "suggested_default": default_val,
                    "message": f"'{key}' must be within the range {value_range}, got {value}."
                }

    if strict:
        extra_keys = set(config.keys()) - set(schema.keys())
        for key in extra_keys:
            problems[key] = {
                "error": "unknown_key",
                "message": f"'{key}' is not defined in the schema."
            }

    return problems

def validate_config(config: dict, schema: dict, strict: bool = True) -> dict:
    """
    Validate `config` against a dict-based schema, returning a new dict 
    that merges defaults and logs warnings for errors. Supports range validation.

    Args:
        config (dict): The configuration to be validated.
        schema (dict): Schema describing expected keys, types, allowed values, and ranges.

    Returns:
        dict: A *merged* config with defaults applied.

    Raises:
        ValueError: If validation fails for any critical (fatal) schema items
    """
    validated_config = {}
    errors = []

    logger.debug('Checking config against schema...')
    for key, rules in schema.items():
        default_val = rules.get('default')
        required = rules.get('required', False)
        allowed = rules.get('allowed')
        value_range = rules.get('range', None)
        description = rules.get('description', 'No description provided')
        fatal = rules.get('fatal', False)


        try:
            expected_type = eval(rules.get('type', 'str'))
        except NameError:
            logger.warning(f"Unknown type in schema for '{key}'. Using 'str'.")
            expected_type = str

        if key not in config:
            if required:
                errors.append(
                    {'key': key,
                     'error': f"'{key}' configuration key is required, but missing. Reasonable value: {default_val}. Description: {description}",
                     'fatal': fatal}
                )
            
            validated_config[key] = default_val
            continue

        value = config[key]
        logger.debug(f'{key}: {value}')
        logger.debug(f'rules:{rules}')

        if not isinstance(value, expected_type):
            expected_names = (
                ', '.join(t.__name__ for t in expected_type)
                if isinstance(expected_type, tuple)
                else expected_type.__name__
            )
            errors.append(
                {'key': key,
                 'error': f"'{key}' must be of type {expected_names}, got {type(value).__name__}.", 
                 'fatal': fatal}
            )
            validated_config[key] = default_val
            continue

        if allowed and value not in allowed:
            errors.append(
                {'key': key,
                 'error': f"'{key}' must be one of {allowed}, got {value}.",
                 'fatal': fatal}
            )
            validated_config[key] = default_val
            continue

        if value_range and isinstance(value, (int, float)):
            min_val, max_val = value_range
            if not (min_val <= value <= max_val):
                errors.append(
                 {'key': key,
                  'error': f"'{key}' must be within the range {value_range}, got {value}.",
                  'fatal': fatal}   
                )
                validated_config[key] = default_val
                continue

        validated_config[key] = value

    # Handle extra keys based on strictness
    extra_keys = set(config.keys()) - set(schema.keys())
    if strict:
        for extra_key in extra_keys:
            logger.warning(f"Extra key '{extra_key}' is not defined in schema and will be removed.")
            logger.debug(f"DEVELOPERS: if you are adding a new configuration key, you must add '{extra_key}' to the appropriate schema file!")
        # No extra keys are added to validated_config in strict mode
    else:
        for extra_key in extra_keys:
            logger.debug(f"Extra key '{extra_key}' in config not in schema. Keeping as-is.")
            validated_config[extra_key] = config[extra_key]

    if errors:
        fatal = False
        logger.warning('Configuration was not valid due to the following problems:')
        for e in errors:
            logger.warning(e['error'])
            if e['fatal']:
                logger.error(f'Fatal configuration error in {e["key"]}')
                fatal = True
            else:
                logger.warning(f'A reasonable value for {e["key"]} was substituted.')
        if fatal:
            raise ValueError(f"Configuration validation failed: {errors}")

    logger.info("Configuration validated successfully.")
    return validated_config, errors


def load_yaml_file(filepath: str) -> dict:
    """
    Safely load a YAML file and return its contents as a dictionary.

    Args:
        filepath (str): Path to the YAML file.

    Returns:
        dict: Parsed contents of the YAML file.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the file cannot be parsed or is not a dictionary.
    """
    path = Path(filepath).expanduser().resolve()

    logger.info(F"Reading yaml file at {path}")

    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")

    try:
        with open(path, 'r',  encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML file '{path}': {e}")

    if not isinstance(data, dict):
        raise ValueError(f"YAML file '{path}' does not contain a valid dictionary.")

    logger.info(f"YAML file '{path}' loaded successfully.")
    return data


def write_yaml_file(filepath: str, data: list, backup: bool = False, keep: int = 2) -> bool:
    """
    Write a list of dictionaries to a YAML file.

    Args:
        filepath (str): The path to the YAML file.
        data (list): List of dictionaries to convert to YAML.

    Returns:
        bool: True if the file was written successfully, False otherwise.

    Raises:
        FileNotFoundError: If the parent directory of the filepath does not exist.
    """
    filepath = Path(filepath).expanduser().resolve()

    # Check if the parent directory exists
    if not filepath.parent.exists():
        raise FileNotFoundError(f"Directory does not exist: {filepath.parent}")
    
    if backup:
        # Perform backup rotation
        for i in reversed(range(1, keep)):
            older = filepath.with_suffix(filepath.suffix + f".{i}")
            newer = filepath.with_suffix(filepath.suffix + f".{i+1}")
            if older.exists():
                older.rename(newer)
        backup_file = filepath.with_suffix(filepath.suffix + ".1")
        if filepath.exists():
            shutil.copy2(filepath, backup_file)

    try:
        # Write to file
        with open(filepath, 'w') as file:
            yaml.dump(data, file, default_flow_style=False, sort_keys=False)
        
        print(f"YAML file successfully written to {filepath}")
        return True
    
    except Exception as e:
        print(f"Failed to write YAML file: {e}")
        return False

def update_yaml_file(filepath: str, changes: Dict[str, Any], *, backup: bool = True, keep: int = 2) -> Tuple[bool, Dict[str, Dict[str, Any]]]:
    """
    Update a YAML file on disk by applying only the changed keys from `changes`.

    This function:
      - Loads the existing YAML as a mapping (dict)
      - Deep-merges `changes` into it
      - Writes back to disk **only if** the merged result differs from the original
      - Optionally rotates backups: file.yaml.1, file.yaml.2, ... (up to `keep`)

    Notes:
      - This uses PyYAML and will not preserve comments. If comment preservation
        is needed, consider switching to `ruamel.yaml`.

    Args:
        filepath: Path to the YAML file to update.
        changes: Dict of updates to apply (only provided keys are updated).
        backup: If True, create a rotated backup before writing.
        keep: Number of rotated backups to retain (>=2 recommended).

    Returns:
        A tuple `(written, diff)` where:
          - `written` indicates whether the file was actually changed and saved.
          - `diff` is a shallow mapping of keys that changed: {key: {from, to}}.
    """
    path = Path(filepath).expanduser().resolve()

    # Load existing YAML (require mapping at top level)
    if path.exists():
        original = load_yaml_file(str(path))
        if not isinstance(original, dict):
            raise ValueError(f"YAML at {path} must be a mapping at the top level")
    else:
        original = {}

    # Merge changes (deep)
    merged = deep_merge(original, changes or {})

    # Compute shallow diff of top-level keys to decide whether to write
    diff: Dict[str, Dict[str, Any]] = {}
    for k, new_v in merged.items():
        old_v = original.get(k)
        if old_v != new_v:
            diff[k] = {"from": old_v, "to": new_v}

    if not diff:
        logger.info(f"No changes detected for {path}; not writing.")
        return False, {}

    # Ensure parent directory exists
    if not path.parent.exists():
        raise FileNotFoundError(f"Directory does not exist: {path.parent}")

    # Optional backup rotation
    if backup:
        for i in reversed(range(1, keep)):
            older = path.with_suffix(path.suffix + f".{i}")
            newer = path.with_suffix(path.suffix + f".{i+1}")
            if older.exists():
                older.rename(newer)
        backup_file = path.with_suffix(path.suffix + ".1")
        if path.exists():
            shutil.copy2(path, backup_file)

    # Write merged mapping
    try:
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(merged, f, sort_keys=False, allow_unicode=True)
        logger.info(f"Updated YAML written to {path}")
        return True, diff
    except Exception as e:
        logger.error(f"Failed to write updated YAML: {e}")
        return False, {}

def make_json_safe(obj):
    """
    Recursively convert a Python object into a JSON-serializable format.
    """
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(v) for v in obj]
    elif isinstance(obj, Path):
        return str(obj)
    else:
        return obj