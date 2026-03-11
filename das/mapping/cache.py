"""Cache utilities for vector tile endpoints.

This module re-exports from utils.cache for backwards compatibility.
New code should import directly from utils.cache.
"""

from utils.cache import (
    VECTOR_TILE_DATA_VERSION_KEY,
    build_tile_cache_key,
    bump_vector_tile_data_version,
    delete_tile_keys_by_prefix,
    get_effective_cache_version,
    get_vector_tile_cache,
    get_vector_tile_data_version,
    invalidate_tile_cache_keys,
)

__all__ = [
    "build_tile_cache_key",
    "get_effective_cache_version",
    "get_vector_tile_cache",
    "get_vector_tile_data_version",
    "bump_vector_tile_data_version",
    "VECTOR_TILE_DATA_VERSION_KEY",
    "delete_tile_keys_by_prefix",
    "invalidate_tile_cache_keys",
]
