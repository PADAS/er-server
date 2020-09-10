import os
import logging
import tempfile
import zipfile

from django.contrib.gis.gdal import DataSource
from django.db import transaction
from mapping.utils import import_feature_types, import_layer

logger = logging.getLogger(__name__)


@transaction.atomic
def process_spatialfile(spatial_file):

    if getattr(spatial_file, 'feature_types_file', None):

        # DataSource requires a file path, regardless of where the data is coming from.
        with tempfile.NamedTemporaryFile('wb') as tf:
            write_contents_to_file(spatial_file.feature_types_file, tf)
            ds = DataSource(tf.name)
            import_feature_types(ds[spatial_file.layer_number])

    df = spatial_file.data

    if df.name.endswith('.zip'):
        # Do it with a temporary directory
        with tempfile.TemporaryDirectory() as workingdir:
            with zipfile.ZipFile(df, 'r') as zip_ref:
                for name in zip_ref.namelist():
                    if name.lower().endswith('.shp') or name.lower().endswith('.gdb'):
                        zip_ref.extractall(workingdir)
                        break

            ds = DataSource(os.path.join(workingdir, name))

            layer_number = 0
            import_layer(ds[layer_number], spatial_file)

    else:
        # DataSource requires a file path, regardless of where the data is coming from.
        with tempfile.NamedTemporaryFile('wb') as tf:
            write_contents_to_file(spatial_file.data, tf)

            ds = DataSource(tf.name)

            if ds.layer_count <= spatial_file.layer_number:
                raise ValueError(f'The layer_number {spatial_file.layer_number} is not valid for this DataSource.')

            layer_number = spatial_file.layer_number
            import_layer(ds[layer_number], spatial_file)


def write_contents_to_file(f, to_file):
    # Convenience function for writing contents to a local file.
    chunk_size = 64 * 2 ** 10
    with f.open('rb') as fo:
        d = fo.read(chunk_size)
        while d:
            to_file.write(d)
            d = fo.read(chunk_size)
        to_file.flush()




