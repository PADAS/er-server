"""Cache utilities for vector tile endpoints.
- Construct stable, low-risk cache keys
- Keep embedding hashing / normalization out of views.
- Do NOT leak bearer tokens or PII into cache keys.
- Keep key length compact while still varying on user, tenant, filters, tile.
- Deterministic ordering of query parameters for consistent hashing
- Versioning for easy cache-busting
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Iterable, Sequence
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.base import InvalidCacheBackendError
from django.http import HttpRequest, QueryDict

logger = logging.getLogger(__name__)


def get_vector_tile_cache():
    """Return the cache instance configured for vector tiles.

    Uses the alias from settings.VECTOR_TILE_CACHE_ALIAS so we do not
    accidentally hit the default cache when a dedicated backend is configured.
    """
    alias = getattr(settings, "VECTOR_TILE_CACHE_ALIAS", "vector_tiles")
    try:
        return caches[alias]
    except (InvalidCacheBackendError, KeyError, AttributeError):
        logger.exception(
            "Vector tile cache alias '%s' is not configured; falling back to default cache",
            alias,
        )
        return caches["default"]


VECTOR_TILE_DATA_VERSION_KEY = "vector_tile_data_version"


def get_vector_tile_data_version() -> int:
    return get_vector_tile_cache().get(VECTOR_TILE_DATA_VERSION_KEY, 0)


def bump_vector_tile_data_version() -> None:
    cache = get_vector_tile_cache()
    try:
        cache.add(VECTOR_TILE_DATA_VERSION_KEY, 0)
        cache.incr(VECTOR_TILE_DATA_VERSION_KEY)
    except Exception:  # pragma: no cover - defensive path
        cache.set(VECTOR_TILE_DATA_VERSION_KEY, int(time.time()), timeout=None)


def get_effective_cache_version():
    """Get the effective cache version combining static setting with dynamic data version."""
    static_version = getattr(settings, "VECTOR_TILE_CACHE_VERSION", "1")
    data_version = get_vector_tile_data_version()
    return f"{static_version}-{data_version}"


def _get_request_tenant(request: HttpRequest) -> str:
    user = getattr(request, "user", None)
    if user is None or getattr(user, "das_tenant_id", None) is None:
        raise ValueError("Cannot create tenant hash: request.user.das_tenant_id is missing")
    return str(user.das_tenant_id)


def _hash_user(request: HttpRequest) -> str:
    user = getattr(request, "user", None)
    if user is None or getattr(user, "id", None) is None:
        raise ValueError("Cannot create user hash: request.user.id is missing")

    user_str = str(user.id)
    return hashlib.sha256(user_str.encode("utf-8")).hexdigest()[
        :8
    ]  # Use first 8 chars for a shorter hash; sufficient for UUID uniqueness in this context


def hash_query_params(querydict: QueryDict) -> str:
    """Produce stable short hash of GET params (multi-value aware).
    Parameter order differences do not affect hash.
    """
    if not querydict:
        return "noquery"
    # Normalise ordering of (key, [values]) then rely on urlencode for canonical form.
    canonical = urlencode(sorted(querydict.lists()), doseq=True)
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()[:10]


def build_tile_cache_key(
    request: HttpRequest,
    z: int,
    x: int,
    y: int,
    layer_ids: Sequence[str] | Iterable[str],
    *,
    cache_version: str = "1",
    include_query: bool = True,
) -> str:
    """Construct a deterministic cache key for a vector tile request.

        * Requires a Bearer token
        * Sorted layer ids (caller order does not fragment cache)
        * Query string hashing is stable (caller order does not fragment cache); can be disabled
          ("include_query=False") when higher fanout is undesirable.

    Key layout
        vt:{tenant}:{layers_csv}:{cache_version}:{z}:{x}:{y}:{user_hash}:{query_hash}

    Returns:
        str: Fully-assembled cache key.
    """
    tenant_component = _get_request_tenant(request)
    user_hash = _hash_user(request)
    query_hash = hash_query_params(request.GET) if include_query else "noquery"
    layers_part = ",".join(sorted(layer_ids)) if layer_ids else "nolayers"

    components = [
        "vt",
        str(tenant_component),
        str(layers_part),
        str(cache_version),
        str(z),
        str(x),
        str(y),
        str(user_hash),
        str(query_hash),
    ]
    cache_key = ":".join(components)
    return cache_key


__all__ = [
    "build_tile_cache_key",
    "get_effective_cache_version",
    "get_vector_tile_cache",
    "get_vector_tile_data_version",
    "bump_vector_tile_data_version",
    "hash_query_params",
    "VECTOR_TILE_DATA_VERSION_KEY",
    "delete_tile_keys_by_prefix",
    "invalidate_tile_cache_keys",
]

# --- Prefix-based invalidation utilities (Redis) ---


def delete_tile_keys_by_prefix(prefix: str) -> int:
    """Delete cache entries whose keys match the given prefix.

    Works with django-redis by using SCAN to avoid blocking. Returns count of deleted keys.
    """
    cache = get_vector_tile_cache()
    deleted = 0
    try:
        client = getattr(cache, "client", None)
        if client is None:
            return 0
        rc = client.get_client(write=True)
        # Use scan_iter for non-blocking iteration
        for key in rc.scan_iter(f"{prefix}*"):
            try:
                rc.delete(key)
                deleted += 1
            except Exception as e:
                # Best-effort: log and continue on individual key deletion failure
                logger.warning(f"Failed to delete cache key {key!r}: {e}", exc_info=True)
    except Exception as e:
        # Best-effort: log so infrastructure issues are visible
        logger.error("delete_tile_keys_by_prefix failed: %s", e, exc_info=True)
        return 0
    return deleted


def invalidate_tile_cache_keys(
    *, tenant_id: str, layer_ids: Sequence[str] | Iterable[str], cache_version: str, z: int, x: int, y: int
) -> int:
    """Invalidate cache entries for a specific tenant/layers/version tile (z/x/y).

    This implementation derives the cache key prefix from build_tile_cache_key layout and deletes matching keys.
    """
    layers_part = ",".join(sorted(layer_ids)) if layer_ids else "nolayers"
    prefix = f"vt:{tenant_id}:{layers_part}:{cache_version}:{z}:{x}:{y}:"
    return delete_tile_keys_by_prefix(prefix)
