from paperpi.library.config_utils import load_yaml_file
from paperpi.library.config_utils import validate_config

def load_app_config(paths: dict):
    file_app_config = paths.get('file_app_config', None)

    app_config = load_yaml_file(file_app_config)
    key = app_config.get('configuration_files', {}).get('key_application_schema', 'main')
    app_config = app_config.get(key, {})

    file_app_schema = paths.get('file_app_schema', None)
    app_schema = load_yaml_file(file_app_schema)
    app_schema = app_schema.get(key, {})

    validated_config = validate_config(config=app_config, schema=app_schema)
    
    return validated_config