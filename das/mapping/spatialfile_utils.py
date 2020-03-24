import io
import logging
import os
import tempfile
import zipfile

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from google.cloud import storage

from mapping.utils import (SPATIAL_FILES_FOLDER, get_datasource_and_layer_num,
                           import_feature_types, import_layer)

logger = logging.getLogger(__name__)


def extract_features_from_files(spatial_file, model):
    try:
        types_file = spatial_file.feature_types_file
    except Exception:
        types_file = None

    if types_file:
        datasource, layer_num = get_and_read_from_upload_file(spatial_file, spatial_file.feature_types_file.name)
        import_feature_types(datasource[layer_num], 'STE')

    datasource, layer_num = get_and_read_from_upload_file(spatial_file, spatial_file.data.name)
    import_layer(datasource[layer_num], spatial_file)

def get_and_read_from_upload_file(spatial_file, filename):
    with default_storage.open(filename) as f:
        with tempfile.NamedTemporaryFile() as data_file:
            data_file.write(f.read())
            data_file.flush()
            data_file.seek(0)

            if filename.lower().endswith('.zip'):
                import_file = extract_zipfile(data_file, filename)
                
            else:
                import_file = data_file.name
            return get_datasource_and_layer_num(import_file, layer=spatial_file.layer_number)

def extract_zipfile(data_file, filename):
    name = filename.split("/")[-1]
    with tempfile.TemporaryDirectory() as tmpdirname: 
        with zipfile.ZipFile(data_file.name, 'r') as zip_ref:
            zip_ref.extractall(tmpdirname)
            import_file = fetch_shape_file_path(tmpdirname)

            # If zip contains a directory encapsulating all the shape files
            if not import_file:
                import_file = fetch_shape_file_path(f'{tmpdirname}/{name[:-4]}')
            return import_file



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
