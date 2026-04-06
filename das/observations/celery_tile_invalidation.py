"""Celery: reset connection-local tile invalidation state for tasks that may use it.

Workers reuse DB connections; any code that appends to the tile batch (see
``segment_tile_cache_invalidation``) stores state on the connection. Signal handlers
that do so are not registered at app startup; this cleanup remains cheap insurance.
"""

from __future__ import annotations

from celery.signals import task_prerun

# Extend when a new Celery package writes those models (see module docstring).
_TILE_INVALIDATION_TASK_NAME_PREFIXES = (
    "analyzers.",
    "observations.",
    "rt_api.",
    "tracking.",
)


def _task_may_use_tile_invalidation_batch(task_name: str) -> bool:
    return task_name.startswith(_TILE_INVALIDATION_TASK_NAME_PREFIXES)


def _clear_stale_tile_invalidation_for_worker_task(sender=None, **kwargs) -> None:
    if sender is None:
        return
    name = getattr(sender, "name", "") or ""
    if not _task_may_use_tile_invalidation_batch(name):
        return
    from observations.segment_tile_cache_invalidation import (
        clear_tile_invalidation_connection_state,
    )

    clear_tile_invalidation_connection_state()


def connect_celery_tile_invalidation_cleanup() -> None:
    task_prerun.connect(_clear_stale_tile_invalidation_for_worker_task, weak=False)
