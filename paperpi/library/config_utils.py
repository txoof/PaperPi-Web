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

logger = logging.getLogger(__name__)


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
                    "message": f"'{key}' is required but missing. Suggested default: {default_val}. {description}"
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
        ValueError: If validation fails for any required or type mismatch.
    """
    validated_config = {}
    errors = []

    for key, rules in schema.items():
        default_val = rules.get('default')
        required = rules.get('required', False)
        allowed = rules.get('allowed')
        value_range = rules.get('range', None)
        description = rules.get('description', 'No description provided')

        try:
            expected_type = eval(rules.get('type', 'str'))
        except NameError:
            logger.warning(f"Unknown type in schema for '{key}'. Using 'str'.")
            expected_type = str

        if key not in config:
            if required:
                errors.append(
                    f"'{key}' configuration key is required, but missing. Reasonable value: {default_val}. Description: {description}"
                )
            validated_config[key] = default_val
            continue

        value = config[key]

        if not isinstance(value, expected_type):
            errors.append(
                f"'{key}' must be of type {expected_type.__name__}, got {type(value).__name__}."
            )
            validated_config[key] = default_val
            continue

        if allowed and value not in allowed:
            errors.append(
                f"'{key}' must be one of {allowed}, got {value}."
            )
            validated_config[key] = default_val
            continue

        if value_range and isinstance(value, (int, float)):
            min_val, max_val = value_range
            if not (min_val <= value <= max_val):
                errors.append(
                    f"'{key}' must be within the range {value_range}, got {value}."
                )
                validated_config[key] = default_val
                continue

        validated_config[key] = value

    # Handle extra keys based on strictness
    extra_keys = set(config.keys()) - set(schema.keys())
    if strict:
        for extra_key in extra_keys:
            logger.warning(f"Extra key '{extra_key}' is not defined in schema and will be removed.")
            logger.debug(f"DEVELOPERS: if you are adding a new configuration key, you must add {extra_key} to the appropriate schema file.")
        # No extra keys are added to validated_config in strict mode
    else:
        for extra_key in extra_keys:
            logger.debug(f"Extra key '{extra_key}' in config not in schema. Keeping as-is.")
            validated_config[extra_key] = config[extra_key]

    if errors:
        for e in errors:
            logger.warning(e)
        raise ValueError(f"Configuration validation failed: {errors}")

    logger.info("Configuration validated successfully.")
    return validated_config


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
