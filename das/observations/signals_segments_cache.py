import logging
import math
from typing import Iterable, List, Set, Tuple

from django.apps import apps
from django.conf import settings
from django.core.signals import request_started
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from utils.cache import get_effective_cache_version, invalidate_tile_cache_keys

logger = logging.getLogger(__name__)

# Reasonable zoom range to consider for invalidation; align to typical vector tile usage
SEGMENTS_TILE_INVALIDATION_ZOOMS = getattr(settings, "SEGMENTS_TILE_INVALIDATION_ZOOMS", range(6, 23))

# Layer IDs must match the ids set on the VectorLayer subclasses used by
# ObservationSegmentTileView.layer_classes so the cache-key prefix matches.
TILE_LAYER_IDS = ("observation_segments", "subjects")

# Connection-local batch: ("p", tenant_id, lon, lat) or ("s", tenant_id, lon1, lat1, lon2, lat2)
_TILE_INV_BATCH_ATTR = "_tile_invalidation_batch"
_TILE_INV_FLUSH_SCHEDULED_ATTR = "_tile_invalidation_flush_scheduled"

# Backward-compatible name for tests
_OBS_TILE_BATCH_ATTR = _TILE_INV_BATCH_ATTR

# Spherical Web Mercator latitude limit (|lat| beyond this has no finite tile y).
_WEB_MERCATOR_MAX_LAT = 85.05112877980659


def lonlat_to_tile_xy(lon: float, lat: float, z: int) -> Tuple[int, int]:
    """Convert WGS84 lon/lat to XYZ tile at zoom z (WebMercator).
    Uses standard slippy map tiling.
    """
    lat = max(-_WEB_MERCATOR_MAX_LAT, min(_WEB_MERCATOR_MAX_LAT, lat))
    lat_rad = math.radians(lat)
    n = int(2**z)
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    xtile = max(0, min(n - 1, xtile))
    ytile = max(0, min(n - 1, ytile))
    return xtile, ytile


def _unwrap_tile_x_for_shortest_path(xa: int, xb: int, z: int) -> Tuple[int, int]:
    """Choose endpoints so Bresenham crosses the shorter horizontal wrap on the WebMercator torus."""
    n = 1 << z
    dx = xb - xa
    half = n // 2
    if dx > half:
        xb -= n
    elif dx < -half:
        xb += n
    return xa, xb


def _bresenham_tile_cells(x0: int, y0: int, x1: int, y1: int, z: int) -> Set[Tuple[int, int]]:
    """Integer Bresenham line in tile space; all cells the segment passes through."""
    n = 1 << z
    cells: Set[Tuple[int, int]] = set()
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        cells.add((x % n, max(0, min(n - 1, y))))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return cells


def tiles_along_segment_at_zoom(lon1: float, lat1: float, lon2: float, lat2: float, z: int) -> Set[Tuple[int, int]]:
    """Tile (x, y) cells at zoom z intersected by the segment in lon/lat (WebMercator tiles).

    Tile x is wrapped so segments crossing the antimeridian follow the shorter path in tile space
    (avoids traversing nearly all x columns at high zoom).
    """
    xa, ya = lonlat_to_tile_xy(lon1, lat1, z)
    xb, yb = lonlat_to_tile_xy(lon2, lat2, z)
    xa, xb = _unwrap_tile_x_for_shortest_path(xa, xb, z)
    return _bresenham_tile_cells(xa, ya, xb, yb, z)


def _invalidate_for_point(*, tenant_id: str, layer_ids: Iterable[str], lon: float, lat: float) -> int:
    deleted = 0
    version = get_effective_cache_version()
    for z in SEGMENTS_TILE_INVALIDATION_ZOOMS:
        x, y = lonlat_to_tile_xy(lon, lat, z)
        deleted += invalidate_tile_cache_keys(
            tenant_id=tenant_id, layer_ids=layer_ids, cache_version=version, z=z, x=x, y=y
        )
    return deleted


def _sync_flush_scheduled_flag_after_rollback(conn) -> None:
    """If the DB rolled back, Django clears on_commit hooks but leaves our connection attrs.

    Without this, _tile_invalidation_flush_scheduled can stay True and block further scheduling.
    """
    if not getattr(conn, _TILE_INV_FLUSH_SCHEDULED_ATTR, False):
        return
    run_on_commit = getattr(conn, "run_on_commit", None)
    if run_on_commit is not None and len(run_on_commit) == 0:
        setattr(conn, _TILE_INV_FLUSH_SCHEDULED_ATTR, False)


def _get_batch(using: str) -> List[Tuple]:
    conn = connections[using]
    _sync_flush_scheduled_flag_after_rollback(conn)
    batch = getattr(conn, _TILE_INV_BATCH_ATTR, None)
    if batch is None:
        batch = []
        setattr(conn, _TILE_INV_BATCH_ATTR, batch)
    return batch


def _schedule_tile_invalidation_flush(using: str) -> None:
    """At most one on_commit callback per DB connection per transaction."""
    conn = connections[using]
    _sync_flush_scheduled_flag_after_rollback(conn)
    if getattr(conn, _TILE_INV_FLUSH_SCHEDULED_ATTR, False):
        return
    setattr(conn, _TILE_INV_FLUSH_SCHEDULED_ATTR, True)

    def _run_flush() -> None:
        setattr(conn, _TILE_INV_FLUSH_SCHEDULED_ATTR, False)
        _flush_batched_tile_invalidations_for_connection(conn)

    transaction.on_commit(_run_flush, using=using)


def _append_point_invalidation(tenant_id: str, lon: float, lat: float, using: str = DEFAULT_DB_ALIAS) -> None:
    _get_batch(using).append(("p", tenant_id, lon, lat))
    _schedule_tile_invalidation_flush(using)


def _append_segment_invalidation(
    tenant_id: str,
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
    using: str = DEFAULT_DB_ALIAS,
) -> None:
    _get_batch(using).append(("s", tenant_id, lon1, lat1, lon2, lat2))
    _schedule_tile_invalidation_flush(using)


def _flush_batched_tile_invalidations_for_connection(conn) -> None:
    """After commit: expand batch to (tenant, z, x, y), dedupe, invalidate once each."""
    batch = getattr(conn, _TILE_INV_BATCH_ATTR, None)
    if batch is None:
        return
    try:
        delattr(conn, _TILE_INV_BATCH_ATTR)
    except AttributeError:
        pass
    if not batch:
        return
    tiles: Set[Tuple[str, int, int, int]] = set()
    for entry in batch:
        kind = entry[0]
        if kind == "p":
            _, tenant_id, lon, lat = entry
            for z in SEGMENTS_TILE_INVALIDATION_ZOOMS:
                x, y = lonlat_to_tile_xy(lon, lat, z)
                tiles.add((tenant_id, z, x, y))
        else:
            _, tenant_id, lon1, lat1, lon2, lat2 = entry
            for z in SEGMENTS_TILE_INVALIDATION_ZOOMS:
                for x, y in tiles_along_segment_at_zoom(lon1, lat1, lon2, lat2, z):
                    tiles.add((tenant_id, z, x, y))

    version = get_effective_cache_version()
    for tenant_id, z, x, y in tiles:
        try:
            invalidate_tile_cache_keys(
                tenant_id=tenant_id,
                layer_ids=TILE_LAYER_IDS,
                cache_version=version,
                z=z,
                x=x,
                y=y,
            )
        except Exception as exc:
            logger.error("Tile cache invalidation failed (batched): %s", exc, exc_info=True)


def _flush_batched_tile_invalidations(using: str = DEFAULT_DB_ALIAS) -> None:
    """Flush batch on the given DB alias (default connection in tests)."""
    _flush_batched_tile_invalidations_for_connection(connections[using])


def _flush_batched_observation_tile_invalidations() -> None:
    """Backward-compatible name for tests."""
    _flush_batched_tile_invalidations()


def clear_tile_invalidation_connection_state() -> None:
    """Drop pending batch and flush flag on all DB connections.

    Call at HTTP request start, after Celery tasks, and in tests — avoids stale state when a
    transaction rolls back (on_commit dropped) but connection-local attrs remain.
    """
    for conn in connections.all():
        for attr in (_TILE_INV_BATCH_ATTR, _TILE_INV_FLUSH_SCHEDULED_ATTR):
            if hasattr(conn, attr):
                delattr(conn, attr)


def clear_observation_tile_invalidation_batch_for_tests() -> None:
    """Backward-compatible name for tests; same as clear_tile_invalidation_connection_state."""
    clear_tile_invalidation_connection_state()


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
