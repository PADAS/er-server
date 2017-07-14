from datetime import datetime
import pytz
import uuid
from functools import partial
from django.conf import settings
from django.db import models
from versatileimagefield.fields import VersatileImageField

from core.models import TimestampedModel
from core.serializers import ContentTypeField

from revision.manager import Revision, RevisionMixin

# Load UserContent settings once from settings.
USERCONTENT_SETTINGS = getattr(settings, 'USERCONTENT_SETTINGS', {})
EDIT_EXTENSIONS = USERCONTENT_SETTINGS.get('edit_extensions', ('html', 'htm', 'js', 'css', 'exe',
                                                               'sh', 'bin', 'dll', 'deb', 'dmg',
                                                               'iso', 'img', 'msi', 'msp', 'msm'))

'''
NOTE: Be sure th configure Nginx to set content-type='application/octet-stream files with executable extension or
 web-content extensions (ex. .exe, .bin, .js, .html)

  For example, if nginx will serve the uploaded content from /var/das/content, set the default_type and types like so:
  
       location /dascontent/ {
                alias /var/dascontent/;
                default_type application/octet-stream;
                types {
                    image/gif gif;
                    image/jpeg jpg jpeg;
                    image/png png;
                    image/tiff tif tiff;
                    application/vnd.openxmlformats-officedocument.wordprocessingml.document    docx;
                    application/vnd.openxmlformats-officedocument.spreadsheetml.sheet          xlsx;
                    application/vnd.openxmlformats-officedocument.presentationml.presentation  pptx;
                }
       }
  
       
'''




def _upload_to(root, instance, filename):
    '''
    This is a hook for providing a filename for uploaded files.
    :param root: root path for file storage.
    :param instance: FileContent instance
    :param filename: default filename
    :return: relative path for storing the file
    '''


    name, extension = filename.rsplit('.', 1) if '.' in filename else (filename, '')

    # Add a .txt extension to anything that a web-server might serve as an executable (ex. js, htm, bin
    if extension in EDIT_EXTENSIONS:
        extension = extension + '.txt'

    d = pytz.utc.localize(datetime.utcnow())
    file_path = '{root}/{year:04}/{month:02}/{day:02}/{pk!s}/{name}.{extension}'.format(root=root, year=d.year, month=d.month,
                                                                                    day=d.day, pk=instance.id,
                                                                                    extension=extension, name=name)
    return file_path

file_content_upload_to = partial(_upload_to, 'file_uploads')
imagefile_content_upload_to = partial(_upload_to, 'image_fileuploads')

class FileContent(TimestampedModel, RevisionMixin):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='file_contents', related_query_name='file_content')
    file = models.FileField(upload_to=file_content_upload_to )
    filename = models.TextField(verbose_name='Name of uploaded file.', default='noname')
    revision = Revision()

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        return result

    def clean(self):
        self.filename = self.file.name
        super().clean()


class ImageFileContent(TimestampedModel, RevisionMixin):
    '''
    Take advantage of VersatileImageField for storing image files and creating appropriate renditions
    of them.
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='imagefile_contents', related_query_name='imagefile_content')

    file = VersatileImageField(upload_to=imagefile_content_upload_to, null=True, max_length=512)
    filename = models.TextField(verbose_name='Name of image file.', default='noname')
    revision = Revision()

    content_type = ContentTypeField()

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        return result

    def clean(self):
        self.filename = self.file.name
        super().clean()


import usercontent.signals