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

# %load_ext autoreload
# %autoreload 2

import logging
from plugin_manager import PluginManager

# +
logger = logging.getLogger('plugin_manager')
logger.setLevel(logging.DEBUG)

# Avoid adding multiple handlers by checking if it already exists
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(levelname)s: [%(funcName)s:%(lineno)d] %(message)s'))
    logger.addHandler(handler)


# +
m = PluginManager()

m.plugin_path = './plugins/'
# m.plugin_path = 123
m.config_path = '../config/'
m.base_schema_file = 'plugin_manager_schema.yaml'
# m.main_schema_file = 'plugin_manager_schema.yaml'
# m.plugin_schema_file = 'plugin_schema.yaml'

config = {
    'screen_mode': 'L',
    'resolution': (300, 160),
}

m.config = config
# -

m.config

configured_plugins = [
    {'plugin': 'basic_clock',
         'base_config': {
            'name': 'Basic Clock',
            'duration': 100,
            # 'refresh_interval': 60,
            # 'dormant': False,
            'layout_name': 'layout',
         }
    },
    # {'plugin': 'debugging',
    #     'base_config': {
    #         'name': 'Debugging 50',
    #         'dormant': True,
    #         'layout': 'layout',
    #         'refresh_interval': 2,
    #     },
    #     'plugin_params': {
    #         'title': 'Debugging 50',
    #         'crash_rate': 0.9,
    #         'high_priority_rate': 0.2,
            
    #     }
    # },
    {'plugin': 'word_clock',
        'base_config':{
            'namex': 'Word Clock',
            'duration': 130,
            'refresh_interval': 60,
            'layout_name': 'layout',
        },
        'plugin_params': {
            'foo': 'bar',
            'spam': 7,
            'username': 'Monty'}
    },
    # {'plugin': 'xkcd_comic',
    #     'base_config': {
    #         'name': 'XKCD',
    #         'duration': 200,
    #         'refresh_interval': 1800,
    #         'dormant': False,
    #         'layout': 'layout'
    #     },
    #     'plugin_params':{
    #         'max_x': 800,
    #         'max_y': 600,
    #         'resize': False,
    #         'max_retries': 5
    #     }
             
    # }
]

m.configured_plugins
