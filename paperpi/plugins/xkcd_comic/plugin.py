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

# your function must import layout and constants
# this is structured to work both in Jupyter notebook and from the command line
try:
    from . import layout
    from . import constants
except ImportError:
    import layout
    import constants
import logging
from random import randint

logger = logging.getLogger(__name__)

import requests
from requests import exceptions as RequestException
from PIL import Image as PILImage


def get_comic_json(url):
    try:
        result = requests.get(url)
    except requests.exceptions.RequestException as e:
        logger.error(f'failed to fetch document at {latest_url}: {e}')
        result = None

    try: 
        json = result.json()
    except (AttributeError, ValueError) as e:
        logger.error(f'failed to decode JSON result possibly due to previous errors: {e}')
        json = {}
    return json


def resize_image(img, target):
    '''resize an image to match target dimensions scaling to the longest side
    
    Args:
        img(PIL Image): pillow image object
        target(tuple of int): target size in pixles'''
    logger.debug('resize image to ')
    
    idx = img.size.index(max(img.size))
    if img.size[idx] < target[idx]:
        r = target[idx]/img.size[idx]
        new_dim = [int(s * r) for s in img.size]
        new_img = img.resize(new_dim, PILImage.LANCZOS)
    else: 
        img.thumbnail(target)
        new_img = img
        
    return new_img


def update_function(self, *args, **kwargs):
    data = {}
    success = False
    latest_url = str.join('/', [constants.xkcd_url, constants.xkcd_json_doc])
    latest_json = get_comic_json(latest_url)
    comic_json = {}
    max_x = self.config.get('max_x', 800)
    max_y = self.config.get('max_y', 600)
    max_retries = self.config.get('max_retries', 10)
    resize = self.config.get('resize', False)

    for i in range(max_retries):
        logger.info(f"Randomly selecting comic from {max_retries} total comics.")
        latest_index = latest_json.get('num', False)
        if latest_index:
            random_index = randint(1, int(latest_index))
        else:
            random_index = constants.default_comic
            logger.error(f"Using default comic due to previous errors: {random_index}")
            continue
        
        random_url = str.join('/', [constants.xkcd_url, str(random_index), constants.xkcd_json_doc])
        comic_json = get_comic_json(random_url)
        
        img_url = comic_json.get('img', None)
        if img_url:
            image_file = self.download_image(img_url)
        else:
            logger.error(f"Failed to download a valid image")
            continue

        if image_file:
            try:
                image = PILImage.open(image_file)
                logger.debug(f"Download image size: image.size")
                if image.size[0] < max_x and image.size[1] < max_y:
                    comic_json['image_file'] = image_file
                    data = comic_json
                    success = True
                else:
                    logger.info("Image exceeds max_x and/or max_y")
                    continue

                if resize:
                    logger.info(f"Upscaling small image to fit {max_x}, {max_y}")
                    resized_img = resize_image(image, (max_x, max_y))
                    resized_img.save(image_file)
                    logger.debug(f'image resized to {resized_img.size}') 
            except Exception as e:
                logger.error(f"Failed to process downloaded file: {e}")
                
    return {'data': data, 'success': success}
