import io
import logging
import os
from zipfile import ZipFile, is_zipfile

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage

from google.cloud import storage
from mapping import utils

logger = logging.getLogger(__name__)

googlestorage = default_storage.__class__.__name__ == 'GoogleCloudStorage'
ste_folder = 'spatialfiles' if googlestorage else 'mapping/spatialfiles'
bucket_name = "kezzy-ste-test"
storage_client = storage.Client()


def extract_features_from_files(spatial_file, model, presentation):
    filepath = spatial_file.data.name
    filename = filepath.split('/')[-1]

    try:
        types_file = spatial_file.feature_types_file
    except Exception:
        types_file = None

    if googlestorage:
        if filename.lower().endswith('.zip'):
            download_file_from_gcp(spatial_file)
            data_file = get_upload_file(spatial_file.data, model, spatial_file.id)
        else:
            data_file = spatial_file.data.url
            feature_types_file = types_file.url if types_file else None
    else:
        data_file = get_upload_file(spatial_file.data, model, spatial_file.id)
        if types_file:
            feature_types_file = get_upload_file(spatial_file.feature_types_file, model, spatial_file.id)

    # extract data from upload file
    if types_file:
        datasource, layer_num = utils.get_datasource_and_layer_num(feature_types_file, spatial_file.layer_number)
        utils.import_feature_types(datasource[layer_num], 'STE')

    if data_file:
        datasource, layer_num = utils.get_datasource_and_layer_num(data_file, spatial_file.layer_number)
        utils.import_layer(datasource[layer_num], spatial_file, presentation)


def get_upload_file(upload_file, model, spatial_file_id):
    if googlestorage:
        uploaded_file_directory = f'{os.getcwd()}/mapping/spatialfiles'
        path = f'mapping/{upload_file.name}'
    else:
        uploaded_file_directory = os.path.dirname(upload_file.path)
        path = upload_file.path

    try:
        return import_spatial_file(path, uploaded_file_directory)
    except ValidationError as err:
        model.objects.filter(id=spatial_file_id).delete()
        raise ValidationError(
            'Error in retrieving features from spatial file:    {}\n '
            'Please verify the spatial file.'.format(err)
        )


def import_spatial_file(uploaded_file_path, uploaded_file_directory):
    """
    Import features by invoking importlayer management command.
    :param uploaded_file_path: Path of uploaded file.
    :param uploaded_file_directory: Directory of uploaded file.
    """
    try:
        import_file = None
        if uploaded_file_path.lower().endswith('.zip'):
            # Extract user-uploaded zip file.
            with ZipFile(
                    uploaded_file_path, 'r') as zip_file_object:
                zip_file_object.extractall(uploaded_file_directory)

            import_file = fetch_shape_file_path(
                uploaded_file_directory)
            # If zip contains a directory encapsulating all the shape files
            if not import_file:
                import_file = fetch_shape_file_path(
                    uploaded_file_path[:-4])
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


def download_file_from_gcp(spatial_file):
    filename = spatial_file.data.name.split('/')[-1]
    blobs = storage_client.list_blobs(bucket_name, prefix=ste_folder)
    for blob in blobs:
        folder = f'mapping/{ste_folder}'
        if not os.path.exists(folder):
            os.makedirs(folder)
        blob.download_to_filename(f'{folder}/{filename}')