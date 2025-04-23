from constants import (PATH_USER_CONFIG, 
                      FNAME_APPLICATION_CONFIG, 
                      FNAME_APPLICATION_SCHEMA,
                      PATH_APP_CONFIG,
                      KEY_APPLICATION_SCHEMA)

from library.config_utils import load_yaml_file
from web.app import app, set_config
from pathlib import Path
import uvicorn

def create_app():
    file_app_config = PATH_USER_CONFIG / FNAME_APPLICATION_CONFIG
    file_app_schema = PATH_APP_CONFIG / FNAME_APPLICATION_SCHEMA
    config = load_yaml_file(file_app_config)
    schema = load_yaml_file(file_app_schema)
    print(config)
    config = config if isinstance(config, dict) and config else {}
    config = config.get(KEY_APPLICATION_SCHEMA, {})
    schema = schema.get(KEY_APPLICATION_SCHEMA, {})
    print(f"[DEBUG] Loaded config from {file_app_config}: {config}")
    set_config(config, schema)
    return app

app = create_app()

if __name__ == '__main__':
    uvicorn.run('web.main:app', host='0.0.0.0', port=8123, reload=True)