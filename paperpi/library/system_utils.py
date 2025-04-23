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

import os


def running_under_systemd():
    """
    A simple heuristic to detect if we're running under systemd.
    If these environment variables are present, systemd likely launched us.
    """
    return ('INVOCATION_ID' in os.environ) or ('JOURNAL_STREAM' in os.environ)
