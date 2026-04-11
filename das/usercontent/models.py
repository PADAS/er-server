import uuid
from datetime import datetime
from functools import partial

import pytz
from django_multitenant.fields import TenantForeignKey
from django_multitenant.mixins import TenantModelMixin
from versatileimagefield.fields import VersatileImageField

from django.conf import settings
from django.db import models

from core.models import TimestampedModel
from core.models.core import DASTenant
from core.serializers import ContentTypeField
from revision.manager import Revision, RevisionMixin
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager
from utils.tenant.thread import get_tenant_settings


def _upload_to(root, instance, filename):
    """
    This is a hook for providing a filename for uploaded files.
    :param root: root path for file storage.
    :param instance: FileContent instance
    :param filename: default filename
    :return: relative path for storing the file
    """

    name, extension = filename.rsplit(".", 1) if "." in filename else (filename, "")

    d = pytz.utc.localize(datetime.utcnow())
    tenant = get_tenant_settings()
    file_path = f"{tenant.slug_name}/{root}/{d.year}/{d.month}/{d.day}/{instance.id}/{name}.{extension}"
    return file_path


file_content_upload_to = partial(_upload_to, "file_uploads")
imagefile_content_upload_to = partial(_upload_to, "image_fileuploads")


class FileContent(TenantModelMixin, TimestampedModel, RevisionMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_by = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="file_contents",
        related_query_name="file_content",
    )
    file = models.FileField(upload_to=file_content_upload_to, max_length=512)
    filename = models.TextField(verbose_name="Name of uploaded file.", default="noname")
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        return result

    def clean(self):
        self.filename = self.file.name
        super().clean()


class ImageFileContent(TenantModelMixin, TimestampedModel, RevisionMixin):
    """
    Take advantage of VersatileImageField for storing image files and creating appropriate renditions
    of them.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_by = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imagefile_contents",
        related_query_name="imagefile_content",
    )

    file = VersatileImageField(upload_to=imagefile_content_upload_to, null=True, max_length=512)
    filename = models.TextField(verbose_name="Name of image file.", default="noname")
    revision = Revision()

    content_type = ContentTypeField()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        return result

    def clean(self):
        self.filename = self.file.name
        super().clean()
