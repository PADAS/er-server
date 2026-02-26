"""
GCS resumable upload helper for chunked file uploads (ERA-9210).

Uses the GCS JSON API resumable upload protocol with google.auth and requests:
(1) initiate(storage_path, total_size) -> session URI
(2) upload_chunk(uri, chunk_bytes, start_byte, total_size) -> None
(3) finalize(uri, total_size) -> complete upload
"""

import json
import logging

from google.auth.transport.requests import AuthorizedSession

from django.conf import settings

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/octet-stream"
UPLOAD_API = "https://www.googleapis.com/upload/storage/v1/b"


def _get_bucket_name() -> str:
    return getattr(settings, "GS_BUCKET_NAME", "earthranger-uploads-default")


def _get_credentials():
    """Credentials for GCS (match TenantGoogleCloudStorage when possible)."""
    storage_class = getattr(settings, "DEFAULT_FILE_STORAGE", "")
    if "TenantGoogleCloudStorage" in str(storage_class):
        from core.storages import TenantGoogleCloudStorage

        store = TenantGoogleCloudStorage()
        return store.get_impersonated_credentials()
    import google.auth

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return creds


def _session() -> AuthorizedSession:
    return AuthorizedSession(_get_credentials())


def initiate(storage_path: str, total_size: int) -> str:
    """
    Start a GCS resumable upload session. Returns the session URI for upload_chunk/finalize.
    """
    bucket = _get_bucket_name()
    url = f"{UPLOAD_API}/{bucket}/o?uploadType=resumable"
    body = json.dumps({"name": storage_path})
    resp = _session().post(
        url,
        data=body,
        headers={"Content-Type": "application/json", "X-Upload-Content-Length": str(total_size)},
        timeout=60,
    )
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
    """Send a chunk to the resumable session. Last chunk completes the upload."""
    end_byte = start_byte + len(chunk_bytes) - 1
    content_range = f"bytes {start_byte}-{end_byte}/{total_size}"
    resp = _session().put(
        uri,
        data=chunk_bytes,
        headers={
            "Content-Length": str(len(chunk_bytes)),
            "Content-Range": content_range,
        },
        timeout=60,
    )
    if resp.status_code in (200, 201):
        return
    if resp.status_code != 308:
        raise RuntimeError(f"Resumable upload chunk failed: {resp.status_code}")


def finalize(uri: str, total_size: int) -> None:
    """Complete the upload (PUT bytes * / total with empty body)."""
    resp = _session().put(
        uri,
        data=b"",
        headers={"Content-Range": f"bytes */{total_size}", "Content-Length": "0"},
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Resumable upload finalize failed: {resp.status_code}")
    logger.info("Resumable upload finalized: %s bytes", total_size)
