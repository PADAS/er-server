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
        vt:{tenant}:{layers_csv}:{cache_version}:{z}:{x}:{y}:{user_hash}:{query_hash}

    Returns:
        str: Fully-assembled cache key.
    """
    tenant_component = _get_request_tenant(request)
    user_hash = _hash_user(request)
    query_hash = _hash_query_params(request.GET) if include_query else "noquery"
    layers_part = ",".join(sorted(layer_ids)) if layer_ids else "nolayers"

    logging.getLogger(__name__)
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


__all__ = ["build_tile_cache_key", "get_effective_cache_version"]
