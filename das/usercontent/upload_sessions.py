"""
Redis-backed session store for chunked, resumable file uploads (ERA-9210).

Key: upload_session:{tenant_id}:{upload_id}. Uses same Redis as CACHES when
configured; distinct KEY_PREFIX. Session TTL from CHUNKED_UPLOAD_SESSION_TTL_SECONDS.
"""

import datetime
import hashlib
import logging
from typing import Any, Optional

from django.conf import settings
from django.core.cache import caches

logger = logging.getLogger(__name__)

CACHE_ALIAS = getattr(settings, "UPLOAD_SESSION_CACHE_ALIAS", "upload_sessions")
TTL = getattr(settings, "CHUNKED_UPLOAD_SESSION_TTL_SECONDS", 86400)


def _cache():
    return caches[CACHE_ALIAS]


def _key(tenant_id: str, upload_id: str) -> str:
    return f"{tenant_id}:{upload_id}"


def create(
    tenant_id: str,
    upload_id: str,
    *,
    storage_path: str,
    filename: str,
    size: int,
    chunk_size: int,
    user_id: Optional[str] = None,
    is_image: bool = False,
    file_content_id: str = "",
) -> None:
    """Create a new upload session. Call set_gcs_uri after initiating resumable upload."""
    data = {
        "gcs_resumable_uri": "",
        "storage_path": storage_path,
        "filename": filename,
        "size": size,
        "chunk_size": chunk_size,
        "next_chunk_index": 0,
        "chunk_hashes": {},
        "user_id": user_id,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "is_image": is_image,
        "file_content_id": file_content_id,
    }
    _cache().set(_key(tenant_id, upload_id), data, timeout=TTL)
    logger.info("Created upload session %s for tenant %s", upload_id, tenant_id)


def get(tenant_id: str, upload_id: str) -> Optional[dict[str, Any]]:
    """Return session data or None if not found/expired."""
    return _cache().get(_key(tenant_id, upload_id))


def set_gcs_uri(tenant_id: str, upload_id: str, uri: str) -> None:
    """Store the GCS resumable session URI after initiate."""
    data = get(tenant_id, upload_id)
    if not data:
        raise ValueError(f"Upload session not found: {upload_id}")
    data["gcs_resumable_uri"] = uri
    _cache().set(_key(tenant_id, upload_id), data, timeout=TTL)


def append_chunk(
    tenant_id: str,
    upload_id: str,
    chunk_index: int,
    chunk_bytes: bytes,
) -> tuple[bool, Optional[str]]:
    """
    Validate order and idempotency; update session for next chunk.

    Returns (accepted, error_message). accepted True means 204 (including idempotent).
    error_message set means 400 with that message.
    """
    data = get(tenant_id, upload_id)
    if not data:
        return False, "Session not found or expired"
    next_idx = data["next_chunk_index"]
    chunk_hashes = data.setdefault("chunk_hashes", {})

    if chunk_index > next_idx:
        return False, "Chunk out of order"
    if chunk_index < next_idx:
        # Already received this index: idempotent only if same bytes
        existing = chunk_hashes.get(chunk_index)
        digest = hashlib.sha256(chunk_bytes).hexdigest()
        if existing == digest:
            return True, None
        return False, "Chunk index already received with different content"

    digest = hashlib.sha256(chunk_bytes).hexdigest()
    chunk_hashes[chunk_index] = digest
    data["next_chunk_index"] = next_idx + 1
    data["chunk_hashes"] = chunk_hashes
    _cache().set(_key(tenant_id, upload_id), data, timeout=TTL)
    return True, None


def delete(tenant_id: str, upload_id: str) -> None:
    """Remove session (e.g. after finalize)."""
    _cache().delete(_key(tenant_id, upload_id))
    logger.info("Deleted upload session %s for tenant %s", upload_id, tenant_id)
