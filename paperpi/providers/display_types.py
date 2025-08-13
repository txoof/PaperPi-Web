from epdlib.Screen import list_compatible_modules

def get_display_types():
    """
    Returns a sanitized list of all compatible EPD modules supported by epdlib.
    """
    names = [i.get('name') for i in list_compatible_modules(False) if i.get('supported')]
    # Normalize IT8951 family names to "HD" for schema/UI simplicity
    norm = ["HD" if (n and "HD IT8951" in n) else n for n in names]
    # De-duplicate while preserving order
    seen = set()
    out = []
    for n in norm:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out