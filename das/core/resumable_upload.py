"""
GCS resumable upload helper for chunked file uploads (ERA-9210).

Uses the GCS JSON API resumable upload protocol with google.auth and requests:
(1) initiate(storage_path, total_size) -> session URI
(2) upload_chunk(uri, chunk_bytes, start_byte, total_size) -> None
(3) abort(uri) -> cancel the resumable session
"""

import json
import logging
import threading

from google.auth.transport.requests import AuthorizedSession

from django.conf import settings

logger = logging.getLogger(__name__)

_tls = threading.local()

CONTENT_TYPE = "application/octet-stream"
UPLOAD_API = "https://www.googleapis.com/upload/storage/v1/b"


def _gcs_timeout() -> int:
    return getattr(settings, "CHUNKED_UPLOAD_GCS_TIMEOUT_SECONDS", 120)


def _get_bucket_name() -> str:
    return getattr(settings, "GS_BUCKET_NAME", "earthranger-uploads-default")


def _get_credentials():
    """Returns the pod's ambient GCS credentials — NOT tenant-scoped.

    Tenant isolation comes from the storage_path prefix (see
    usercontent.storage_paths.build_usercontent_storage_path), not from credentials.
    The per-thread AuthorizedSession cached in _session() relies on this invariant:
    if this function is ever changed to return tenant-specific credentials, that
    cache becomes a cross-tenant leak and must be reworked (e.g. keyed by tenant_id,
    or rebuilt per request).
    """
    storage_class = getattr(settings, "DEFAULT_FILE_STORAGE", "")
    if "TenantGoogleCloudStorage" in str(storage_class):
        from core.storages import TenantGoogleCloudStorage

        store = TenantGoogleCloudStorage()
        return store.get_impersonated_credentials()
    import google.auth

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return creds


def _session() -> AuthorizedSession:
    """One AuthorizedSession per thread (requests.Session is not thread-safe)."""
    sess = getattr(_tls, "authorized", None)
    if sess is None:
        sess = AuthorizedSession(_get_credentials())
        _tls.authorized = sess
    return sess


def initiate(
    storage_path: str,
    total_size: int,
    *,
    content_type: str | None = None,
    content_disposition: str | None = None,
) -> str:
    """
    Start a GCS resumable upload session. Returns the session URI for upload_chunk/abort.

    content_type / content_disposition: optional GCS object metadata to set on the
    finalized object. Used to force browsers to download (rather than render) active
    content like SVG/HTML/JS when fetched directly from GCS.
    """
    bucket = _get_bucket_name()
    url = f"{UPLOAD_API}/{bucket}/o?uploadType=resumable"
    payload: dict[str, str] = {"name": storage_path}
    if content_type:
        payload["contentType"] = content_type
    if content_disposition:
        payload["contentDisposition"] = content_disposition
    body = json.dumps(payload)
    headers = {"Content-Type": "application/json", "X-Upload-Content-Length": str(total_size)}
    if content_type:
        headers["X-Upload-Content-Type"] = content_type
    resp = _session().post(url, data=body, headers=headers, timeout=_gcs_timeout())
    resp.raise_for_status()
    location = resp.headers.get("Location")
    if not location:
        raise RuntimeError("Resumable upload initiate did not return Location header")
    logger.info("Initiated resumable upload for %s (%s bytes)", storage_path, total_size)
    return location


def upload_chunk(
    uri: str,
    chunk_bytes: bytes,
    start_byte: int,
    total_size: int,
) -> None:
    """
    Send a chunk to the resumable session.

    Intermediate chunks typically receive HTTP 308 (Resume Incomplete). The final
    chunk (this PUT covers the last byte of ``total_size``) must receive 200/201 when
    the object is complete; 308 on the final chunk means the object was not written.
    """
    end_byte = start_byte + len(chunk_bytes) - 1
    content_range = f"bytes {start_byte}-{end_byte}/{total_size}"
    resp = _session().put(
        uri,
        data=chunk_bytes,
        headers={
            "Content-Length": str(len(chunk_bytes)),
            "Content-Range": content_range,
        },
        timeout=_gcs_timeout(),
    )
    if resp.status_code in (200, 201):
        return
    is_final_chunk = start_byte + len(chunk_bytes) == total_size
    if resp.status_code == 308:
        if is_final_chunk:
            raise RuntimeError(
                "Resumable upload final chunk returned 308 Resume Incomplete; "
                "object not finalized (expected 200 or 201)."
            )
        return
    raise RuntimeError(f"Resumable upload chunk failed: {resp.status_code}")


def abort(uri: str) -> None:
    """
    Cancel a GCS resumable upload session.

    Issues DELETE to the session URI per GCS resumable upload protocol. GCS returns 499
    (Client Closed Request) on successful cancellation — this is the expected response
    and is treated as success, not an error. Any other non-successful status is logged as
    a warning; abort failures are non-fatal (the session will expire on the GCS side).
    """
    resp = _session().delete(uri, timeout=_gcs_timeout())
    if resp.status_code == 499:
        logger.info("Aborted GCS resumable upload session")
        return
    if resp.status_code not in (200, 204):
        logger.warning("GCS resumable abort returned unexpected status: %s", resp.status_code)
