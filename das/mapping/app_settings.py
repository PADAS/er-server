import os

from django.conf import settings

MBTILES_ID_PATTERN = r'[\.\-_0-9a-zA-Z]+'
MBTILES_CATALOG_PATTERN = MBTILES_ID_PATTERN
MBTILES_DEFAULT = {'root': os.path.join(settings.MEDIA_ROOT, 'mbtiles'),
                   'tile_size': 256,
                   'ext': 'mbtiles',
                   'missing_tile_404': False}

MBTILES = MBTILES_DEFAULT


def reload():
    global MBTILES
    mbtiles = getattr(settings, 'MAPPING', {})
    if 'MBTILES' in mbtiles:
        mbtiles = mbtiles['MBTILES']
        MBTILES = {k: mbtiles.get(k, v) for k, v in MBTILES_DEFAULT.items()}


reload()

