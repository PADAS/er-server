import os
import zipfile

from django.http import HttpResponse
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
import time


class FileCompression:

    static_path = 'sprite-src/{0}'
    image_types = ('svg', 'png', 'jpg')

    def __init__(self, list_of_files):
        self.list_files = list_of_files
        self.file_paths = self.get_file_path()

    def lookup_file_path(self, file_name):
        static_file = self.static_path.format(file_name)

        file_path = finders.find(static_file)
        return file_path

    def get_file_path(self):
        file_format = '{filename}.{ext}'
        file_paths = []

        for file_name in self.list_files:
            for ext in self.image_types:
                _file = file_format.format(
                    **dict(filename=file_name['icon'], ext=ext))
                file_path = self.lookup_file_path(_file)

                if file_path:
                    file_paths.append(file_path)
        return file_paths

    def zip_compress(self, zip_subdir):
        zipfile_name = "{0}.zip".format(zip_subdir)

        response = HttpResponse(content_type='application/zip')
        with zipfile.ZipFile(response, 'w') as zip_file:
            for _file in self.file_paths:
                file_dir, filename = os.path.split(_file)
                zip_path = os.path.join(zip_subdir, filename)

                zip_file.write(_file, zip_path)

        response['Content-Disposition'] = 'attachment; filename={}'.format(
            zipfile_name)
        return response
