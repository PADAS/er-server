import io
import logging
import os
import zipfile

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from google.cloud import storage

from mapping.utils import (get_datasource_and_layer_num, import_feature_types,
                           import_layer, SPATIAL_FILES_FOLDER)

logger = logging.getLogger(__name__)

onlinestorage = default_storage.__class__.__name__ != 'FileSystemStorage'

def extract_features_from_files(spatial_file, model):
    try:
        types_file = spatial_file.feature_types_file
    except Exception:
        types_file = None

    if onlinestorage:
        create_spatialfiles_folder()
        download_files(spatial_file, types_file)
    data_file = get_upload_file(spatial_file.data, model, spatial_file.id)
    if types_file:
        feature_types_file = get_upload_file(types_file, model, spatial_file.id)
        datasource, layer_num = get_datasource_and_layer_num(feature_types_file, layer=spatial_file.layer_number)
        import_feature_types(datasource[layer_num], 'STE')

    if data_file:
        datasource, layer_num = get_datasource_and_layer_num(data_file, layer=spatial_file.layer_number)
        import_layer(datasource[layer_num], spatial_file)

def create_spatialfiles_folder():
    if not os.path.exists(SPATIAL_FILES_FOLDER):
            os.makedirs(SPATIAL_FILES_FOLDER)

def get_upload_file(upload_file, model, spatial_file_id):
    if onlinestorage:
        path = f'mapping/{upload_file.name}'
    else:
        path = upload_file.path

    try:
        return import_spatial_file(path)
    except ValidationError as err:
        model.objects.filter(id=spatial_file_id).delete()
        raise ValidationError(
            'Error in retrieving features from spatial file:    {}\n '
            'Please verify the spatial file.'.format(err)
        )


def import_spatial_file(uploaded_file_path):
    """
    Import features from file.
    :param uploaded_file_path: Path of uploaded file.
    """
    try:
        import_file = None
        if uploaded_file_path.lower().endswith('.zip'):
            # Extract user-uploaded zip file.
            if not onlinestorage:
                with zipfile.ZipFile(uploaded_file_path, 'r') as zip_file_object:
                    zip_file_object.extractall(SPATIAL_FILES_FOLDER)

            import_file = fetch_shape_file_path(SPATIAL_FILES_FOLDER)
            # If zip contains a directory encapsulating all the shape files
            if not import_file:
                import_file = fetch_shape_file_path(uploaded_file_path[:-4])
        else:
            import_file = uploaded_file_path

        if import_file:
            return import_file
        else:
            raise ValidationError(
                f'Unsupported file, or incomplete archive file uploaded {uploaded_file_path}')
    except Exception as err:
        logger.error(err)
        raise ValidationError(err)


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


def download_files(spatial_file, types_file):

    files = [spatial_file.data]

    if types_file:
        files.append(spatial_file.feature_types_file)

    for upload_file in files:
        try:
            request = requests.get(upload_file.url)
            name = upload_file.name

            if upload_file.name.lower().endswith('.zip'):
                downloaded_zip = zipfile.ZipFile(io.BytesIO(request.content), 'r')
                downloaded_zip.extractall(SPATIAL_FILES_FOLDER)
            else:
                with open(f'{SPATIAL_FILES_FOLDER}/{name.split("/")[-1]}', 'w+') as fd:
                    fd.write(request.content.decode())
        except Exception as ex:
            logger.exception(ex)
