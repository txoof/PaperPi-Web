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

# +
#code snip that makes path work so package imports and relative imports work
# both in jupyter and as a script

import sys
from pathlib import Path

def in_notebook() -> bool:
    try:
        from IPython import get_ipython  # noqa: F401
        return True
    except Exception:
        return False

def here_dir() -> Path:
    # When executed as a script, __file__ exists
    if '__file__' in globals():
        return Path(__file__).resolve().parent
    # In a notebook, fall back to the current working directory
    return Path.cwd().resolve()

def find_project_root(start: Path, markers=('pyproject.toml', 'setup.cfg', '.git', 'paperpi')):
    cur = start
    for _ in range(20):  # safety bound
        # if any marker file or directory exists here, treat this as root
        if any((cur / m).exists() for m in markers):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None

# 1) Determine where we are
_nb_or_script_dir = here_dir()

# 2) Locate the project root by walking upward until we find a marker
_project_root = find_project_root(_nb_or_script_dir)

# 3) Add paths in the right order
#    - Ensure local directory is first so 'import constants' resolves locally
#    - Ensure project root is also present so package imports work
paths_to_add = []
if str(_nb_or_script_dir) not in sys.path:
    paths_to_add.append(str(_nb_or_script_dir))
if _project_root and str(_project_root) not in sys.path:
    paths_to_add.append(str(_project_root))

# Prepend to sys.path, preserving existing entries
sys.path[:0] = paths_to_add

# +
import logging
from datetime import datetime
from time import time
import random
from pathlib import Path

from paperpi.library.base_plugin import BasePlugin
# -

# two different import modes for development or distribution
try:
    # import from other modules above this level
    from . import layout
    from . import constants
except ImportError:
    import constants
    # development in jupyter notebook
    import layout


logger = logging.getLogger(__name__)


def remove_non_alphanumeric(s):
    # Using list comprehension to filter out non-alphanumeric characters
    filtered_string = ''.join([char for char in s if char.isalnum()])
    return filtered_string


class Plugin(BasePlugin):
    """
    Basic Clock plugin: renders time

    Expects BasePlugin to provide:
      - self.name
      - self.screen_mode, self.layout (optional usage)
      - any config/params via self.config / self.params 
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info('Initing basic_clock plugin instance')
        
    def update_data(self, *, now: str | None = None, **kwargs) -> dict:
        """
        update function for debugging plugin provides title, time, crash rate
    
        This plugin shows minimal data and is designed to throw exceptions to test other functionality. 
        The plugin will deliberately and randomly throw exceptions at the rate specified in the configuration. 
        When an exception is not thrown, the plugin will randomly change its priority to the max set in the 
        configuration. Set the rate at which the plugin should jump to the higher priority status in the configuration.
        
        
        Args:
            title(`str`): title of plugin to display
            crash_rate(`float`): value between 0 and 1 indicating probability of throwing 
                exception on execution
        """

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
