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


logger = logging.getLogger(__name__)

try:
    from . import constants
    logger.info('production load')
except ImportError:
    import constants
    logger.info('jupyter development load')


def update_function(self, *args, **kwargs):
    '''update function for basic_clock provides system time string in the format HH:MM
    
    Args:
        None
    
    Returns:
        tuple: (is_updated(bool), data(dict), priority(int))
    %U'''
    data = {'digit_time': datetime.now().strftime("%H:%M")}

    return {'data': data, 'success': True}
