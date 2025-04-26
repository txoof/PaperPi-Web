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
import sys

from paperpi.constants import LOG_FORMAT, DATE_FORMAT


# +

def setup_logging(level=logging.INFO):
    # Set up the root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create a console handler
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)
    
    # Attach the handler to the root logger
    logger.addHandler(handler)

    # Test logging from the main program
    logger.info("Logger setup complete. Ready to capture logs.")
    
    # Test logging from a simulated library
    library_logger = logging.getLogger("library.plugin_manager")

    return logger

# logger = setup_logging()
# -


