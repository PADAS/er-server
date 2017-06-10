from datetime import datetime
import pytz
import uuid
from django.conf import settings
from django.db import models

from core.models import TimestampedModel
from revision.manager import Revision, RevisionMixin

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

SUPPORTED_EXTENSIONS = ('pdf', 'doc', 'docx', 'txt', 'csv', 'xls', 'xlsx', 'pptx', 'ppt', 'jpg', 'png', 'svg', 'jpeg',
                        'gif', 'tif', 'tiff')

# Edit the extensions in this list -- add a .txt as a safeguard in case the web-server is not configured to set
# the content-type appropriately.
EDIT_EXTENSIONS = ('html', 'htm', 'js', 'css', 'exe', 'sh', 'bin', 'dll', 'deb', 'dmg', 'iso', 'img', 'msi', 'msp',
                   'msm')


def upload_to(instance, filename):
    '''
    This is a hook for providing a filename for upload content.
    :param instance: FileContent instance
    :param filename: default filename
    :return: relative path for storing the file
    '''


    name, extension = filename.rsplit('.', 1) if '.' in filename else (filename, '')

    # Add a .txt extension to anything that a web-server might serve as an executable (ex. js, htm, bin
    if extension in EDIT_EXTENSIONS:
        extension = extension + '.txt'

    d = pytz.utc.localize(datetime.utcnow())
    file_path = 'file_uploads/{year:04}/{month:02}/{day:02}/{pk!s}/{name}.{extension}'.format(year=d.year, month=d.month,
                                                                                    day=d.day, pk=instance.id,
                                                                                    extension=extension, name=name)
    return file_path

class FileContent(TimestampedModel, RevisionMixin):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='file_contents', related_query_name='file_content')
    file = models.FileField(upload_to=upload_to, )
    filename = models.TextField(verbose_name='Name of uploaded file.', default='noname')
    revision = Revision()

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        # self.event.dependent_table_updated()
        return result

    def clean(self):
        self.filename = self.file.name

        # TODO: This validation on .content_type is too easy to circumvent, so instead (see above) the file's extension
        #       gets changed when it's saved.
        #       Consider adding logic to read the uploaded file to determine it's content and take appropriate aciton.

        # try:
        #     if self.file.file.content_type not in SUPPORTED_CONTENT_TYPES:
        #         raise ValueError('This file\'s type is not supported.')
        # except AttributeError:
        #     pass

        super().clean()
