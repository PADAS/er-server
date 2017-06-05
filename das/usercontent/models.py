from datetime import datetime
import pytz
import uuid
from django.conf import settings
from django.db import models

from core.models import TimestampedModel

def upload_to(instance, filename):
    '''
    This is a hook for providing a filename for upload content.
    :param instance: FileContent instance
    :param filename: default filename
    :return: relative path for storing the file
    '''
    name, extension = filename.rsplit('.', 1) if '.' in filename else (filename, '')

    d = pytz.utc.localize(datetime.utcnow())
    file_path = 'file_uploads/{year:04}/{month:02}/{day:02}/{pk!s}.{extension}'.format(year=d.year, month=d.month,
                                                                                    day=d.day, pk=instance.id,
                                                                                    extension=extension)
    return file_path

class FileContent(TimestampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='file_contents', related_query_name='file_content')
    file = models.FileField(upload_to=upload_to, )
    filename = models.TextField(verbose_name='Name of uploaded file.', default='noname')

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        # self.event.dependent_table_updated()
        return result

    def clean(self):
        self.filename = self.file.name
        super().clean()
