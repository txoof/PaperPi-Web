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
# # %cd /home/pi/src/PaperPi-Web

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

import logging
from datetime import datetime
from random import choice
from copy import deepcopy


from paperpi.library.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

try:
    from . import constants
except ImportError:
    import constants


def _time_list(time):
    '''Returns time as list [h, m] of type int
    
    Args:
        time(`str`): time in colon separated format - 09:34; 23:15'''
    return  [int(i)  for i in time.split(':')]


def _time_now():
    return datetime.now().strftime("%H:%M")


def _map_val(a, b, s):
    '''map range `a` to `b` for value `s`

    Args:
        a(2 `tuple` of `int`): (start, end) of input values
        b(2 `tuple` of `int`): (start, end) of output values
        s(`float`, `int`): value to map
    Returns:
        `int`'''
    a1, a2 = a
    b1, b2 = b
    
    t = b1 + ((s-a1) * (b2-b1))/(a2-a1)
    
    return round(t)


class Plugin(BasePlugin):
    """
    Word Clock plugin: renders time as words.

    Expects BasePlugin to provide:
      - self.name
      - self.screen_mode, self.layout (optional usage)
      - any config/params via self.config / self.params if your BasePlugin exposes them
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info('Initing word_clock plugin instance')
        
    def update_data(self, *, now: str | None = None, **kwargs) -> dict:
        """
        Provide the time as a word string such as:
        - The time is around ten twenty
        - It's about twenty after eight

        Returns:
            dict like {'data': {...}, 'success': True, 'high_priority': False}        
        """

        logger.info(f'update_data for {self.name}')
        hours = constants.HOURS
        minutes = constants.MINUTES
        stems = constants.STEMS

        # allow injecting a time string for testing
        use_time = now or _time_now()
        t_list = _time_list(use_time)
        logger.debug(f'using time: {use_time}')

        # map minute into 0..6 bucket so we can say, "about ten", etc.
        minute_bucket = _map_val((1, 59), (0, 6), t_list[1])

        # choose hour: 0..34 -> current hour; 35..59 -> next hour (wrap at 24)
        if t_list[1] <= 34:
            hour_str_list = hours[str(t_list[0])]
        else:
            try:
                hour_str_list = hours[str(t_list[0] + 1)]
            except KeyError:
                # wrap around to zeroth index in the hours list
                hour_str_list = hours[str(0)]

        min_str_list = minutes[str(minute_bucket)]

        # build the time string
        if minute_bucket in (0, 6): # o'clock
            time_str = f"{choice(hour_str_list).title()} {choice(min_str_list).title()}"
        else:
            time_str = f"{choice(min_str_list).title()} {choice(hour_str_list).title()}"

        data = {
            "wordtime": f"{choice(stems)} {time_str}",
            "time": use_time,
        }
        return {"data": data, "success": True, "high_priority": False}
