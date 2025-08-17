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
from paperpi.library.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

import requests
from requests import exceptions as RequestException
from PIL import Image as PILImage
from PIL import ImageFile as PILImageFile


def get_comic_json(url):
    try:
        result = requests.get(url)
    except requests.exceptions.RequestException as e:
        logger.error(f'failed to fetch document at {url}: {e}')
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


def probe_remote_image_size(url: str, session: requests.Session | None = None, max_bytes: int = 65536) -> tuple[int, int] | None:
    """
    Try to discover remote image dimensions by fetching only an initial byte range.
    Returns (width, height) if determinable, else None.
    Does not write to disk and does not cache.
    """
    s = session or requests.Session()
    headers = {'Range': f'bytes=0-{max_bytes-1}'}
    try:
        resp = s.get(url, headers=headers, stream=True, timeout=15)
        resp.raise_for_status()
    except RequestException as e:
        logger.error(f'failed to probe image size: {e}')
        return None
    parser = PILImageFile.Parser()
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            try:
                parser.feed(chunk)
            except Exception:
                # keep feeding; some formats need more data
                pass
            try:
                im = parser.image
            except Exception:
                im = None
            if im is not None and im.size is not None:
                return im.size
    except RequestException as e:
        logger.error(f'error while probing image: {e}')
        return None
    return None


class Plugin(BasePlugin):
    """
    Fetch random XKCD comics with dimensions <= those specified

    Expects BasePlugin to provide:
      - self.name
      - self.screen_mode, self.layout (optional usage)
      - any config/params via self.config / self.params 
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
    def update_data(self, *, now: str | None = None, **kwargs) -> dict:
        """
        Provide random comic from XKCD

        Returns:
            dict like {'data': {...}, 'success': True, 'high_priority': False}        
        """

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
            logger.debug(f'Attempt {i} of {max_retries}')
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
            if not img_url:
                logger.error("No image URL in comic JSON")
                continue

            # Probe dimensions of remote image prior to downloading entire document
            size = probe_remote_image_size(img_url)
            logger.info(f'size of {img_url}: {size}')
            if size is None:
                logger.info("Could not determine size from remote; skipping")
                continue

            w, h = size
            if w > max_x or h > max_y:
                logger.info(f'Skipping {img_url} due to size {w}x{h} exceeding {max_x}x{max_y}')
                continue

            # within bounds use downloader to cache
            image_file = self.download_image(img_url)
            if not image_file:
                logger.error("Download failed!")
                continue
            try:
                with PILImage.open(image_file) as image:
                    logger.debug(f'Downloaded image size: {image.size}')
                comic_json['image_file'] = image_file
                data = comic_json
                if resize:
                    logger.info(f'Upscaling small image to fit {max_x}x{max_y}')
                    resized_img = resize
                    resized_img.save(image_file)
                success = True
                break
            except Exception as e:
                logger.error(f'Failed to process downloaded file: {e}')
                continue
                    
        return {'data': data, 'success': success, 'high_priority': False}
