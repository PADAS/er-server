"""
Build storage paths for usercontent File/Image fields (aligned with upload_to).

Used by chunked uploads so the GCS resumable object name matches the path stored on the model.
"""

import mimetypes
import uuid
from datetime import datetime, timezone

from django.conf import settings

from utils.tenant.thread import get_tenant_settings


def build_usercontent_storage_path(file_content_id: uuid.UUID, filename: str, *, uploads_root: str) -> str:
    """
    Mirror usercontent.models._upload_to(root, instance, filename) using a known id.

    uploads_root: "file_uploads" or "image_fileuploads"
    """
    name, extension = filename.rsplit(".", 1) if "." in filename else (filename, "")

    d = datetime.now(tz=timezone.utc)
    tenant = get_tenant_settings()
    return f"{tenant.slug_name}/{uploads_root}/{d.year}/{d.month}/{d.day}/{file_content_id}/{name}.{extension}"


def is_image_filename(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    image_exts = getattr(settings, "USERCONTENT_SETTINGS", {}).get(
        "imagefile_extensions", ("jpg", "jpeg", "png", "gif", "tif", "tiff")
    )
    return ext in image_exts


def force_download_content_headers(filename: str) -> tuple[str | None, str | None]:
    """Return (content_type, content_disposition) overrides for filenames whose mime type
    is in USERCONTENT_SETTINGS["force_download_mimetypes"], else (None, None).

    Used to stamp safe metadata on the storage object so that direct fetches (e.g. signed
    GCS URLs) do not let browsers render active content like SVG/HTML/JS inline.
    """
    force_download = set(getattr(settings, "USERCONTENT_SETTINGS", {}).get("force_download_mimetypes", ()))
    if not force_download:
        return None, None
    mt, _ = mimetypes.guess_type(filename)
    if mt and mt in force_download:
        return "application/octet-stream", "attachment"
    return None, None
