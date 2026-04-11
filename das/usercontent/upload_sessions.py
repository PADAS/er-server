"""
Redis-backed session store for chunked, resumable file uploads (ERA-9210).

Application code addresses sessions by the fragment ``{tenant_id}:{upload_id}`` (see
``_key``). The actual backend key stored in Redis/memcache is derived by the configured
cache alias in ``CACHES[UPLOAD_SESSION_CACHE_ALIAS]`` and may be transformed by a custom
``KEY_FUNCTION`` (for example ``utils.tenant.cache.make_cache_key``), so operators should
inspect cache settings rather than assume a literal ``KEY_PREFIX:{tenant_id}:{upload_id}``
shape.

``django_redis`` exposes ``cache.lock`` for distributed locking; LocMem (tests/dev
single-process) uses a per-session ``threading.Lock`` fallback — see ``session_write_lock``.
Session TTL from ``CHUNKED_UPLOAD_SESSION_TTL_SECONDS``.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import logging
import threading
from typing import Any, Iterator, Optional

from django.conf import settings
from django.core.cache import caches

logger = logging.getLogger(__name__)

CACHE_ALIAS = getattr(settings, "UPLOAD_SESSION_CACHE_ALIAS", "upload_sessions")
TTL = getattr(settings, "CHUNKED_UPLOAD_SESSION_TTL_SECONDS", 86400)

_thread_lock_registry_guard = threading.Lock()
_thread_locks: dict[tuple[str, str], threading.Lock] = {}


def _cache():
    return caches[CACHE_ALIAS]


def _key(tenant_id: str, upload_id: str) -> str:
    return f"{tenant_id}:{upload_id}"


def _thread_lock_for_session(tenant_id: str, upload_id: str) -> threading.Lock:
    """Return a process-local lock for (tenant_id, upload_id); creation is serialized."""
    key = (tenant_id, upload_id)
    with _thread_lock_registry_guard:
        if key not in _thread_locks:
            _thread_locks[key] = threading.Lock()
        return _thread_locks[key]


@contextlib.contextmanager
def session_write_lock(tenant_id: str, upload_id: str) -> Iterator[None]:
    """
    Serialize session mutations for one upload (chunk append, finalize/delete).

    Uses Redis distributed locks when the cache backend supports ``.lock``; otherwise a
    process-local lock so tests and single-worker dev remain correct under concurrency.
    """
    cache = _cache()
    lock_key = f"session_write:{tenant_id}:{upload_id}"
    if hasattr(cache, "lock"):
        # Hold long enough for a slow GCS resumable PUT; block long enough for overlapping retries.
        with cache.lock(lock_key, timeout=300, blocking_timeout=300):
            yield
    else:
        with _thread_lock_for_session(tenant_id, upload_id):
            yield


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
    gcs_resumable_uri: str = "",
) -> None:
    """Create a new upload session with the GCS resumable URI set atomically at creation."""
    data = {
        "gcs_resumable_uri": gcs_resumable_uri,
        "storage_path": storage_path,
        "filename": filename,
        "size": size,
        "chunk_size": chunk_size,
        "next_chunk_index": 0,
        "chunk_hashes": {},
        "user_id": user_id,
        "created_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "is_image": is_image,
        "file_content_id": file_content_id,
    }
    _cache().set(_key(tenant_id, upload_id), data, timeout=TTL)
    logger.info("Created upload session %s for tenant %s", upload_id, tenant_id)


def get(tenant_id: str, upload_id: str) -> Optional[dict[str, Any]]:
    """Return session data or None if not found/expired.

    On a cache miss (TTL expiry or explicit delete) clean up any stale process-local
    lock entry so the _thread_locks registry does not grow without bound.
    """
    data = _cache().get(_key(tenant_id, upload_id))
    if data is None:
        key = (tenant_id, upload_id)
        with _thread_lock_registry_guard:
            _thread_locks.pop(key, None)
    return data


def append_chunk(
    tenant_id: str,
    upload_id: str,
    chunk_index: int,
    chunk_bytes: bytes,
) -> tuple[bool, Optional[str]]:
    """
    Validate order and idempotency; update session for next chunk.

    Call only while ``session_write_lock(tenant_id, upload_id)`` is held (view layer).

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
            _cache().set(_key(tenant_id, upload_id), data, timeout=TTL)
            return True, None
        return False, "Chunk index already received with different content"

    digest = hashlib.sha256(chunk_bytes).hexdigest()
    chunk_hashes[chunk_index] = digest
    data["next_chunk_index"] = next_idx + 1
    data["chunk_hashes"] = chunk_hashes
    _cache().set(_key(tenant_id, upload_id), data, timeout=TTL)
    return True, None


def delete(tenant_id: str, upload_id: str) -> None:
    """Remove session (e.g. after finalize). Drops the LocMem fallback lock entry if present."""
    _cache().delete(_key(tenant_id, upload_id))
    key = (tenant_id, upload_id)
    with _thread_lock_registry_guard:
        _thread_locks.pop(key, None)
    logger.info("Deleted upload session %s for tenant %s", upload_id, tenant_id)
