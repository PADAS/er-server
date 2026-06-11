"""Domain-level helpers for the usercontent app.

Lives in usercontent/ (not das/utils/) because these functions are aware of
FileContent / ImageFileContent models and USERCONTENT_SETTINGS — domain-specific
concepts that must not leak into the app-agnostic utils package.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from django.conf import settings

from usercontent import upload_sessions
from usercontent.models import FileContent, ImageFileContent
from utils.tenant.thread import get_tenant_settings

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

USERCONTENT_SETTINGS: dict[str, Any] = getattr(settings, "USERCONTENT_SETTINGS", {})

_AUDIO_EXTENSIONS: frozenset[str] = frozenset(USERCONTENT_SETTINGS.get("audio_extensions", ()))
_DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(USERCONTENT_SETTINGS.get("document_extensions", ()))
_IMAGE_EXTENSIONS: frozenset[str] = frozenset(USERCONTENT_SETTINGS.get("image_extensions", ()))
_VIDEO_EXTENSIONS: frozenset[str] = frozenset(USERCONTENT_SETTINGS.get("video_extensions", ()))

FileTypeLabel = Literal["audio", "document", "image", "video"]


def classify_file_type(filename: str) -> FileTypeLabel | None:
    """Return the UI file-type category for *filename*, or ``None`` if unknown.

    Extension lookup is case-insensitive and uses the buckets defined in
    ``USERCONTENT_SETTINGS``.  Returns one of ``"audio"``, ``"document"``,
    ``"image"``, ``"video"``, or ``None`` when the extension matches no bucket.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _AUDIO_EXTENSIONS:
        return "audio"
    if ext in _DOCUMENT_EXTENSIONS:
        return "document"
    if ext in _IMAGE_EXTENSIONS:
        return "image"
    if ext in _VIDEO_EXTENSIONS:
        return "video"
    return None


def resolve_usercontent_for_user(
    usercontent_id: object,
    user: AbstractBaseUser,
) -> FileContent | ImageFileContent | None:
    """Look up a usercontent record owned by *user* in the current tenant.

    Checks ``FileContent`` first, then ``ImageFileContent``.  Returns the
    first matching instance, or ``None`` if neither model has a matching
    record for this user/tenant combination.

    This function never raises — callers are responsible for deciding
    whether ``None`` maps to HTTP 404 or HTTP 400.
    """
    instance = FileContent.objects.filter(id=usercontent_id, created_by=user).first()
    if instance is not None:
        return instance
    return ImageFileContent.objects.filter(id=usercontent_id, created_by=user).first()


def resolve_attachment_filename_for_user(
    usercontent_id: object,
    user: AbstractBaseUser,
) -> str | None:
    """Return the filename of an attachment the *user* is allowed to reference.

    Accepts an **initiated** chunked-upload (live Redis session) OR a **finalized**
    FileContent/ImageFileContent row.  Ownership is enforced in both cases; tenant
    isolation on the session lookup is automatic via the cache KEY_FUNCTION.  Returns
    None when neither an owned session nor an owned DB row exists.
    """
    tenant_id = str(get_tenant_settings().id)
    session = upload_sessions.get(tenant_id, str(usercontent_id))
    if session is not None and session.get("user_id") == str(user.pk):
        return session.get("filename")

    instance = resolve_usercontent_for_user(usercontent_id, user)
    if instance is not None:
        return instance.filename
    return None


def resolve_usercontent_for_tenant(
    usercontent_id: object,
) -> FileContent | ImageFileContent | None:
    """Look up a usercontent record in the current tenant by ID, without user filtering.

    Checks ``FileContent`` first, then ``ImageFileContent``.  Tenant isolation
    is automatic via ``CommonTenantManager``.  Returns the first matching instance,
    or ``None`` if neither model has a matching record for this tenant.

    This function never raises — callers are responsible for deciding whether
    ``None`` maps to HTTP 404 or some other response.
    """
    instance = FileContent.objects.filter(id=usercontent_id).first()
    if instance is not None:
        return instance
    return ImageFileContent.objects.filter(id=usercontent_id).first()


@dataclass
class AttachmentInfo:
    """Resolved status and metadata for a usercontent attachment."""

    status: str
    file_type: FileTypeLabel | None
    filename: str | None
    has_renditions: bool = False


def get_attachment_info(usercontent_id: object) -> AttachmentInfo:
    """Return status and metadata for a usercontent attachment UUID.

    Resolution order:
    1. Finalized ``FileContent`` / ``ImageFileContent`` row in the tenant →
       ``status="complete"``.
    2. Non-expired Redis upload session in the tenant → ``status="in_progress"``.
    3. Neither found → ``status="unknown"``.

    ``file_type`` and ``filename`` are populated for ``complete`` and
    ``in_progress`` statuses, and ``None`` for ``unknown``.

    ``has_renditions`` is ``True`` only when the finalized row is an
    ``ImageFileContent`` instance.  Files stored as plain ``FileContent``
    (e.g. ``.webp``, ``.heic``, ``.bmp``) classify as ``file_type="image"``
    but are not processed through the image pipeline, so no renditions exist
    and ``has_renditions`` is ``False`` for them.
    """
    instance = resolve_usercontent_for_tenant(usercontent_id)
    if instance is not None:
        return AttachmentInfo(
            status="complete",
            file_type=classify_file_type(instance.filename),
            filename=instance.filename,
            has_renditions=isinstance(instance, ImageFileContent),
        )

    tenant_id = str(get_tenant_settings().id)
    session = upload_sessions.get(tenant_id, str(usercontent_id))
    if session is not None:
        filename = session.get("filename") or ""
        return AttachmentInfo(
            status="in_progress",
            file_type=classify_file_type(filename) if filename else None,
            filename=filename or None,
            has_renditions=False,
        )

    return AttachmentInfo(status="unknown", file_type=None, filename=None, has_renditions=False)


def guess_content_type(filename: str) -> str:
    """Return a MIME type for *filename*, falling back to ``application/octet-stream``.

    Uses the stdlib ``mimetypes`` module; no external calls.
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"
