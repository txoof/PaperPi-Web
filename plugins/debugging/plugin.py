# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:light
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
from datetime import datetime
from time import time
import random
from pathlib import Path

# two different import modes for development or distribution
try:
    # import from other modules above this level
    from . import layout
    from . import constants
except ImportError:
    import constants
    # development in jupyter notebook
    import layout


# +
# import sys
# # fugly hack for making the library module available to the plugins
# sys.path.append(layout.dir_path+'/../..')
# -

logger = logging.getLogger(__name__)


def remove_non_alphanumeric(s):
    # Using list comprehension to filter out non-alphanumeric characters
    filtered_string = ''.join([char for char in s if char.isalnum()])
    return filtered_string


def update_function(self, title=None, crash_rate=None, max_priority_rate=None, *args, **kwargs):
    '''update function for debugging plugin provides title, time, crash rate
    
    This plugin shows minimal data and is designed to throw exceptions to test other functionality. 
    The plugin will deliberately and randomly throw exceptions at the rate specified in the configuration. 
    When an exception is not thrown, the plugin will randomly change its priority to the max set in the 
    configuration. Set the rate at which the plugin should jump to the higher priority status in the configuration.
    
    
    Args:
        self(`namespace`)
        title(`str`): title of plugin to display
        crash_rate(`float`): value between 0 and 1 indicating probability of throwing 
            exception on execution
    %U'''

    crash = False
    success = False
    title = self.config.get('title', None)
    max_priority_rate = self.config.get('max_priority_rate', None)
    crash_rate = self.config.get('crash_rate', None)
    
    if not title:
        constants.default_title

    if not crash_rate:
        crash_rate = constants.default_crash_rate

    if not max_priority_rate:
        max_priority_rate = constants.default_max_priority_rate
    
    random.seed(time())
    rand_crash = random.random()
    rand_priority = random.random()


    logger.info(f'rand_priority: {rand_priority}, max_priority_rate: {max_priority_rate}')
    
    if rand_priority <= max_priority_rate:
        high_priority = True
    else:
        high_priority = False

    logger.info(f"high_priority mode: {high_priority}")
    
    data = {
        'title': f'{title}',
        'crash_rate': f'Crash Rate: {crash_rate*100:.0f}%',
        'digit_time': datetime.now().strftime("%H:%M:%S"),
        'priority': f'high_priority: {high_priority}',
    }

    if rand_crash <= crash_rate:
        logger.info('Random CRASH!')
        crash = True
    
    if crash:
        raise Exception(f'random crash occured')
    else:
        success = True
        
    is_updated = True
    return {'data': data, 'success': success, 'high_priority': high_priority}

