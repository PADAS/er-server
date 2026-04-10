"""Django signal handlers for segment vector tile cache invalidation (optional).

This module is **not** imported from ``ObservationsConfig.ready()`` so production web
workers and Celery processes do not register these handlers. Import it explicitly in
tests (or a future Celery-based invalidation worker) when hook registration is desired.

See ``segment_tile_cache_invalidation`` for the implementation and
``docs/plans/observation-segment-tile-cache-invalidation-celery.md`` for the async plan.
"""

import logging

from django.apps import apps
from django.core.signals import request_started
from django.db import DEFAULT_DB_ALIAS
from django.db.models.signals import post_save
from django.dispatch import receiver

from observations.segment_tile_cache_invalidation import (
    _append_point_invalidation,
    _append_segment_invalidation,
    clear_tile_invalidation_connection_state,
)

logger = logging.getLogger(__name__)


@receiver(request_started)
def _clear_stale_observation_tile_batch(sender, **kwargs) -> None:
    """Avoid unbounded batch growth on pooled connections if a txn rolled back without commit."""
    clear_tile_invalidation_connection_state()


Observation = apps.get_model("observations", "Observation")
ObservationSegment = apps.get_model("observations", "ObservationSegment")
SubjectStatus = apps.get_model("observations", "SubjectStatus")


@receiver(post_save, sender=Observation)
def invalidate_segment_tiles_on_observation_change(sender=None, instance=None, using=None, **kwargs):
    """Invalidate vector tile cache when an observation changes.

    Batched and deferred until transaction commit so bulk ingests (e.g. 200 points)
    perform one deduped Redis pass instead of one scan per observation per zoom.
    """
    try:
        if not instance or not instance.location:
            return
        lon = float(instance.location.x)
        lat = float(instance.location.y)
        tenant_id = str(instance.das_tenant_id)
        db = using or DEFAULT_DB_ALIAS
        _append_point_invalidation(tenant_id, lon, lat, using=db)
    except Exception as exc:
        logger.error("Tile cache invalidation failed on Observation change: %s", exc, exc_info=True)


@receiver(post_save, sender=ObservationSegment)
def invalidate_segment_tiles_on_segment_change(sender=None, instance=None, using=None, **kwargs):
    """Invalidate vector tile cache when a segment changes (all tiles along the line)."""
    try:
        if not instance:
            return
        tenant_id = str(instance.das_tenant_id)
        db = using or DEFAULT_DB_ALIAS
        a = instance.start_observation.location
        b = instance.end_observation.location
        if a and b:
            _append_segment_invalidation(
                tenant_id,
                float(a.x),
                float(a.y),
                float(b.x),
                float(b.y),
                using=db,
            )
        elif a:
            _append_point_invalidation(tenant_id, float(a.x), float(a.y), using=db)
        elif b:
            _append_point_invalidation(tenant_id, float(b.x), float(b.y), using=db)
    except Exception as exc:
        logger.error("Tile cache invalidation failed on ObservationSegment change: %s", exc, exc_info=True)


@receiver(post_save, sender=SubjectStatus)
def invalidate_subject_tiles_on_status_change(sender=None, instance=None, using=None, **kwargs):
    """Invalidate vector tile cache when a SubjectStatus changes."""
    try:
        if not instance or not instance.location:
            return
        lon = float(instance.location.x)
        lat = float(instance.location.y)
        tenant_id = str(instance.das_tenant_id)
        db = using or DEFAULT_DB_ALIAS
        _append_point_invalidation(tenant_id, lon, lat, using=db)
    except Exception as exc:
        logger.error("Tile cache invalidation failed on SubjectStatus change: %s", exc, exc_info=True)
