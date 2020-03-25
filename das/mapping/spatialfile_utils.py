import logging
import os
import tempfile
import zipfile

from django.core.files.storage import default_storage

from mapping.utils import (get_datasource_and_layer_num, DEFAULT_SOURCE_NAME,
                           import_feature_types, import_layer)

logger = logging.getLogger(__name__)


def extract_features_from_files(spatial_file, model):
    try:
        types_file = spatial_file.feature_types_file
    except Exception:
        types_file = None

    if types_file:
        datasource, layer_num = get_and_read_from_upload_file(spatial_file, spatial_file.feature_types_file.name)
        import_feature_types(datasource[layer_num], DEFAULT_SOURCE_NAME)

    datasource, layer_num = get_and_read_from_upload_file(spatial_file, spatial_file.data.name)
    import_layer(datasource[layer_num], spatial_file)


def get_and_read_from_upload_file(spatial_file, filename):
    with default_storage.open(filename) as f:
        if filename.lower().endswith('.zip'):
            return extract_zipfile(filename, f)
        else:
            with tempfile.NamedTemporaryFile() as data_file:
                data_file.write(f.read())
                data_file.flush()
                data_file.seek(0)
                return get_datasource_and_layer_num(data_file.name, layer=spatial_file.layer_number)


def extract_zipfile(filename, f):
    with tempfile.TemporaryDirectory() as tmpdirname:
        with zipfile.ZipFile(f, 'r') as zip_ref:
            zip_ref.extractall(tmpdirname)
            import_file = fetch_shape_file_path(tmpdirname)

            # If zip contains a directory encapsulating all the shape files
            if not import_file:
                name = filename.split("/")[-1]
                import_file = fetch_shape_file_path(f'{tmpdirname}/{name[:-4]}')
            return get_datasource_and_layer_num(import_file, layer=0)


def fetch_shape_file_path(directory_path):
    """
    Fetch shape file path from the given directory.
    :param directory_path: Directory to iterate through.
    :return: Path of the shape file.
    """
    import_file = None
    for file_name in os.listdir(directory_path):
        if file_name.lower()[-4:] in ['.shp', '.gdb']:
            import_file = os.path.join(directory_path, file_name)
            break
    return import_file
