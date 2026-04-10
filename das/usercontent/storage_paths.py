"""
Build storage paths for usercontent File/Image fields (aligned with upload_to).

Used by chunked uploads so the GCS resumable object name matches the path stored on the model.
"""

import uuid
from datetime import datetime

import pytz

from django.conf import settings

from utils.tenant.thread import get_tenant_settings


def build_usercontent_storage_path(file_content_id: uuid.UUID, filename: str, *, uploads_root: str) -> str:
    """
    Mirror usercontent.models._upload_to(root, instance, filename) using a known id.

    uploads_root: "file_uploads" or "image_fileuploads"
    """
    name, extension = filename.rsplit(".", 1) if "." in filename else (filename, "")

    # Match FileContent/ImageFileContent: naive UTC converted to aware UTC (historical behavior).
    d = datetime.now(tz=pytz.utc)
    tenant = get_tenant_settings()
    return f"{tenant.slug_name}/{uploads_root}/{d.year}/{d.month}/{d.day}/{file_content_id}/{name}.{extension}"


def is_image_filename(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    image_exts = getattr(settings, "USERCONTENT_SETTINGS", {}).get(
        "imagefile_extensions", ("jpg", "jpeg", "png", "gif", "tif", "tiff")
    )
    return ext in image_exts
