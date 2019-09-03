import os
import zipfile

from django.http import HttpResponse
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders


class ZipFileCompression:
    image_types = ('svg', 'png', 'jpg')
    image_icons = []

    def __init__(self, list_files):
        self.files = list_files

    def check_file_type(self):
        file_format = '{filename}.{ext}'

        for file_name in self.files:
            for ext in ZipFileCompression.image_types:
                file_ = file_format.format(
                    **dict(filename=file_name['icon'], ext=ext))
                self.check_file_exist(file_)
        return self.image_icons

    def check_file_exist(self, file_):
        static_paths = ('{0}', 'sprite-src/{0}')

        for static_path in static_paths:
            static_file = static_path.format(file_)

            if finders.find(static_file):
                path = staticfiles_storage.path(static_file)
                self.image_icons.append(path)

    def zip_compress(self, list_files):
        zip_subdir = "choices_icons"
        zipfile_name = "{0}.zip".format(zip_subdir)

        response = HttpResponse(content_type='application/zip')
        with zipfile.ZipFile(response, 'w') as zip_file:
            for file_ in list_files:
                file_dir, filename = os.path.split(file_)
                zip_path = os.path.join(zip_subdir, filename)

                zip_file.write(file_, zip_path)
        response['Content-Disposition'] = 'attachment; filename={}'.format(
            zipfile_name)
        return response
