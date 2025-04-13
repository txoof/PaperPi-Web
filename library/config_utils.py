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

logger = logging.getLogger(__name__)


def validate_config(config: dict, schema: dict) -> dict:
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
            # Gather helpful info from the schema
            default_val = rules.get('default')
            required = rules.get('required', False)
            allowed = rules.get('allowed')
            value_range = rules.get('range', None)  # Range for numerical values
            description = rules.get('description', 'No description provided')
    
            # Convert string type to actual Python type
            try:
                expected_type = eval(rules.get('type', 'str'))
            except NameError:
                logger.warning(f"Unknown type in schema for '{key}'. Using 'str'.")
                expected_type = str
    
            # Handle missing required keys
            if key not in config:
                if required:
                    errors.append(
                        f"'{key}' configuration key is required, but missing. Reasonable value: {default_val}. Description: {description}"
                    )
                validated_config[key] = default_val
                continue
    
            # Key is present in user's config
            value = config[key]
    
            # Type validation
            if not isinstance(value, expected_type):
                errors.append(
                    f"'{key}' must be of type {expected_type}, got {type(value).__name__}."
                )
                validated_config[key] = default_val
                continue
    
            # Allowed value validation
            if allowed and value not in allowed:
                errors.append(
                    f"'{key}' must be one of {allowed}, got {value}."
                )
                validated_config[key] = default_val
                continue
    
            # Range validation for numerical types (int, float)
            if value_range and isinstance(value, (int, float)):
                min_val, max_val = value_range
                if not (min_val <= value <= max_val):
                    errors.append(
                        f"'{key}' must be within the range {value_range}, got {value}."
                    )
                    validated_config[key] = default_val
                    continue
    
            # Store valid values
            validated_config[key] = value
    
        # Log and keep extra keys that aren't in the schema
        for extra_key in config.keys() - schema.keys():
            logger.debug(f"Extra key '{extra_key}' in config not in schema. Keeping as-is.")
            validated_config[extra_key] = config[extra_key]
    
        # If errors occurred, raise collectively
        if errors:
            for e in errors:
                logger.warning(e)
            raise ValueError(f"Configuration validation failed: {e}")
    
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


def write_yaml_file(filepath: str, data: list) -> bool:
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
    
    try:
        # Write to file
        with open(filepath, 'w') as file:
            yaml.dump(data, file, default_flow_style=False, sort_keys=False)
        
        print(f"YAML file successfully written to {filepath}")
        return True
    
    except Exception as e:
        print(f"Failed to write YAML file: {e}")
        return False


