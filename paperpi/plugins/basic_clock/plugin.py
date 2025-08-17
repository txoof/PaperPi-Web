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

import logging
from datetime import datetime


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
# -

from paperpi.library.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

try:
    from . import constants
    logger.info('production load')
except ImportError:
    import constants
    logger.info('jupyter development load')


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
        Provide the time as digits

        Returns:
            dict like {'data': {...}, 'success': True, 'high_priority': False}        
        """
        
        data = {'digit_time': datetime.now().strftime("%H:%M")}
    
        return {'data': data, 'success': True, 'high_priority': False}
