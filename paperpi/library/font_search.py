import paperpi

from pathlib import Path

def get_root():
    return Path(paperpi.__file__).resolve().parent

def locate_path(name='fonts', max_depth=3):
    root = get_root()
    for p in root.rglob('*'):
        if p.is_dir() and name.lower() in p.name.lower():
            if len(p.relative_to(root).parts) <= max_depth:
                return p
    return None