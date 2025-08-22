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
from typing import Iterable, List, Mapping, Protocol, Sequence, Union
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest


def get_effective_cache_version():
    """Get the effective cache version combining static setting with dynamic data version."""
    static_version = getattr(settings, "VECTOR_TILE_CACHE_VERSION", "1")
    data_version = cache.get("vector_tile_data_version", 0)
    return f"{static_version}-{data_version}"


def _hash_token(auth_header: str) -> str:
    """Return short stable hash fragment for an Authorization header.

    Raises:
        ValueError: If header missing / not Bearer / token empty.
    """
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise ValueError("Missing or invalid bearer token")
    parts = auth_header.split(None, 1)
    if len(parts) < 2:
        raise ValueError("Empty bearer token")
    token = parts[1].strip()
    if not token:
        raise ValueError("Empty bearer token")
    return hashlib.sha1(token.encode("utf-8")).hexdigest()[:16]


QueryParams = Union["_QueryDictLike", Mapping[str, Sequence[str]]]


class _QueryDictLike(Protocol):  # pragma: no cover - structural typing only
    """Subset of django.http.QueryDict we rely on (lists() method)."""

    def lists(self) -> Iterable[tuple[str, List[str]]]:  # noqa: D401
        ...


def _hash_query_params(get_params: QueryParams) -> str:
    """Produce stable short hash of GET params (multi-value aware)
    parameter order differences do not affect/change hash
    """
    if not get_params:
        return "noquery"
    # Normalise ordering of (key, [values]) then rely on urlencode for canonical form.
    canonical = urlencode(sorted(get_params.lists()), doseq=True)
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
        vt:cv{cache_version}:{layers_csv}:{z}:{x}:{y}:{tenant}:{token_hash}:{query_hash}

    Returns:
        str: Fully-assembled cache key.
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION") or request.META.get("authorization", "")
    token_hash = _hash_token(auth_header)
    user = getattr(request, "user", None)
    tenant_component = getattr(user, "das_tenant_id", "no_tenant") or "no_tenant"
    query_hash = _hash_query_params(request.GET) if include_query else "noquery"
    layers_part = ",".join(sorted(layer_ids)) if layer_ids else "nolayers"

    import logging

    logger = logging.getLogger(__name__)
    components = [
        f"vt:{tenant_component}",
        str(token_hash),
        str(cache_version),
        str(layers_part),
        str(z),
        str(x),
        str(y),
        str(query_hash),
    ]
    cache_key = ":".join(components)
    logger.info(f"Vector tile cache key: {cache_key}")
    return cache_key


__all__ = ["build_tile_cache_key", "get_effective_cache_version"]
