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


def _coerce_vector_tile_cache_int(value: object, *, fallback: int = 0) -> int:
    """Normalize values from cache.get(); backends may deserialize as str or bytes."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return fallback
    if isinstance(value, (bytes, bytearray)):
        try:
            return int(value.decode("utf-8").strip())
        except (ValueError, UnicodeDecodeError):
            return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


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
    raw = get_vector_tile_cache().get(VECTOR_TILE_DATA_VERSION_KEY, 0)
    return _coerce_vector_tile_cache_int(raw, fallback=0)


def bump_vector_tile_data_version() -> None:
    cache = get_vector_tile_cache()
    try:
        cache.add(VECTOR_TILE_DATA_VERSION_KEY, 0, timeout=None)
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


OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX = "obs_seg_tile_ver"


def get_observation_segment_tile_version(tenant_id: str) -> int:
    """Return the per-tenant observation segment tile version (0 if never bumped)."""
    key = f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tenant_id}"
    raw = get_vector_tile_cache().get(key, 0)
    return _coerce_vector_tile_cache_int(raw, fallback=0)


def bump_observation_segment_tile_version(tenant_id: str) -> None:
    """Increment the per-tenant segment tile version so cached tiles become stale.

    Called on observation delete/update (rare operations) — NOT on creates (the hot
    path).  One atomic Redis INCR replaces the old per-tile Bresenham SCAN/DELETE.
    """
    vt_cache = get_vector_tile_cache()
    key = f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tenant_id}"
    try:
        vt_cache.add(key, 0, timeout=None)
        vt_cache.incr(key)
    except Exception:  # pragma: no cover - defensive path
        vt_cache.set(key, int(time.time()), timeout=None)


def get_observation_segment_cache_version(tenant_id: str) -> str:
    """Cache version string for observation segment tiles.

    Combines the global effective version (shared with SpatialFeature tiles) with a
    per-tenant segment counter that is bumped only on deletes/edits.
    """
    base = get_effective_cache_version()
    seg_ver = get_observation_segment_tile_version(tenant_id)
    return f"{base}-s{seg_ver}"


# --- Generic scoped tile-version counters (app-agnostic) ---


def _scoped_tile_version_key(prefix: str, *key_parts: str) -> str:
    return f"{prefix}:" + ":".join(key_parts)


def get_scoped_tile_version(prefix: str, *key_parts: str) -> int:
    """Return a scoped tile-version counter (0 if never bumped).

    Generic O(1) version counter for vector-tile cache-busting. Callers compose a
    ``prefix`` plus arbitrary ``key_parts`` (e.g. tenant id, user id) to namespace
    the counter; this module attaches no domain meaning to those parts. The
    ``vector_tiles`` cache alias is namespaced by hand (it does not use
    ``make_cache_key``), so callers include any tenant scoping in ``key_parts``.
    """
    key = _scoped_tile_version_key(prefix, *key_parts)
    raw = get_vector_tile_cache().get(key, 0)
    return _coerce_vector_tile_cache_int(raw, fallback=0)


def bump_scoped_tile_version(prefix: str, *key_parts: str) -> None:
    """Increment a scoped tile-version counter so matching cached tiles become stale.

    One atomic Redis INCR; no TTL. Mirrors the defensive fallback used by the
    observation-segment counter (``set(time())`` if INCR is unavailable).
    """
    vt_cache = get_vector_tile_cache()
    key = _scoped_tile_version_key(prefix, *key_parts)
    try:
        vt_cache.add(key, 0, timeout=None)
        vt_cache.incr(key)
    except Exception:  # pragma: no cover - defensive path
        vt_cache.set(key, int(time.time()), timeout=None)


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
    "OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX",
    "get_observation_segment_tile_version",
    "bump_observation_segment_tile_version",
    "get_observation_segment_cache_version",
    "get_scoped_tile_version",
    "bump_scoped_tile_version",
]

# --- Prefix-based invalidation utilities (Redis) ---


def delete_tile_keys_by_prefix(prefix: str) -> int:
    """Delete cache entries whose keys match the given prefix.

    Works with django-redis by using SCAN to avoid blocking. Returns count of deleted keys.
    The prefix is run through cache.make_key() so that KEY_PREFIX and VERSION
    from the backend configuration are included in the scan pattern.
    """
    cache = get_vector_tile_cache()
    deleted = 0
    try:
        client = getattr(cache, "client", None)
        if client is None:
            return 0
        rc = client.get_client(write=True)
        redis_prefix = cache.make_key(prefix) if hasattr(cache, "make_key") else prefix
        for key in rc.scan_iter(f"{redis_prefix}*"):
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
