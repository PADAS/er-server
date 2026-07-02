"""Activity-domain vector-tile cache versioning (ERA-11809).

Composes the generic, app-agnostic scoped version-counter primitive in
``utils.cache`` with activity domain meaning:

- a **per-tenant event-data** counter, bumped on event update/delete (never on
  create — that is the hot path; new events reach the map via the realtime socket
  and the short tile TTL); folded together with
- the **per-user (identity)** counter owned by ``accounts.tile_cache`` (bumped on
  token-delete / permission change). Importing it here keeps the dependency
  pointing activity -> accounts.

``get_event_tile_cache_version`` folds both, plus the global effective version,
into the ``cache_version`` string passed to ``build_tile_cache_key``.
"""

from __future__ import annotations

from accounts.tile_cache import get_user_tile_version
from utils.cache import (
    bump_scoped_tile_version,
    get_effective_cache_version,
    get_scoped_tile_version,
)

EVENT_TILE_DATA_VERSION_KEY_PREFIX = "event_tile_data_ver"


def get_event_tile_data_version(tenant_id: str) -> int:
    """Return the per-tenant event-tile data version (0 if never bumped)."""
    return get_scoped_tile_version(EVENT_TILE_DATA_VERSION_KEY_PREFIX, tenant_id)


def bump_event_tile_data_version(tenant_id: str) -> None:
    """Increment the per-tenant event-tile data version so cached tiles become stale.

    Called on event update/delete (the relatively rare path) — NOT on creates (the
    hot path), which would collapse the cache hit rate tenant-wide.
    """
    bump_scoped_tile_version(EVENT_TILE_DATA_VERSION_KEY_PREFIX, tenant_id)


def get_event_tile_cache_version(tenant_id: str, user_id: str) -> str:
    """Cache version string for event tiles.

    Combines the global effective version with a per-user counter (bumped on
    token-delete / permission change → invalidates only that user's event tiles)
    and a per-tenant event-data counter (bumped on event update/delete →
    invalidates the tenant's event tiles tenant-wide; creates rely on socket + TTL).
    """
    base = get_effective_cache_version()
    user_ver = get_user_tile_version(tenant_id, user_id)
    data_ver = get_event_tile_data_version(tenant_id)
    return f"{base}-u{user_ver}-d{data_ver}"


__all__ = [
    "EVENT_TILE_DATA_VERSION_KEY_PREFIX",
    "get_event_tile_data_version",
    "bump_event_tile_data_version",
    "get_event_tile_cache_version",
]
