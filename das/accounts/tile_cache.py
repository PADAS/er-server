"""Accounts-domain (per-user identity) vector-tile cache versioning (ERA-11809).

A per-user version counter, bumped when a user's identity/permissions change
(token-delete, permission-set membership/contents change), so only that user's
cached tiles are invalidated — in O(1), without scanning the keyspace.

Composes the generic, app-agnostic scoped version-counter primitive in
``utils.cache``. Lives in ``accounts`` (next to its consumer, the accounts
signals) so accounts does not depend on activity; activity composes this with its
event-data counter (activity -> accounts, the correct dependency direction).
"""

from __future__ import annotations

from utils.cache import bump_scoped_tile_version, get_scoped_tile_version

USER_TILE_VERSION_KEY_PREFIX = "user_tile_ver"


def get_user_tile_version(tenant_id: str, user_id: str) -> int:
    """Return the per-user tile version (0 if never bumped)."""
    return get_scoped_tile_version(USER_TILE_VERSION_KEY_PREFIX, tenant_id, user_id)


def bump_user_tile_version(tenant_id: str, user_id: str) -> None:
    """Increment a single user's tile version so their cached tiles become stale.

    Called on token-delete / permission change — invalidates only that user's
    tiles in O(1).
    """
    bump_scoped_tile_version(USER_TILE_VERSION_KEY_PREFIX, tenant_id, user_id)


__all__ = [
    "USER_TILE_VERSION_KEY_PREFIX",
    "get_user_tile_version",
    "bump_user_tile_version",
]
