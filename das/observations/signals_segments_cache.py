import logging
import math
from typing import Iterable, Tuple

from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from mapping.cache import get_effective_cache_version, invalidate_tile_cache_keys

# Reasonable zoom range to consider for invalidation; align to typical vector tile usage
SEGMENTS_TILE_INVALIDATION_ZOOMS = getattr(settings, "SEGMENTS_TILE_INVALIDATION_ZOOMS", range(6, 23))


def lonlat_to_tile_xy(lon: float, lat: float, z: int) -> Tuple[int, int]:
    """Convert WGS84 lon/lat to XYZ tile at zoom z (WebMercator).
    Uses standard slippy map tiling.
    """
    lat_rad = math.radians(lat)
    n = 2.0**z
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return xtile, ytile


def _invalidate_for_point(*, tenant_id: str, layer_ids: Iterable[str], lon: float, lat: float) -> int:
    deleted = 0
    version = get_effective_cache_version()
    for z in SEGMENTS_TILE_INVALIDATION_ZOOMS:
        x, y = lonlat_to_tile_xy(lon, lat, z)
        deleted += invalidate_tile_cache_keys(
            tenant_id=tenant_id, layer_ids=layer_ids, cache_version=version, z=z, x=x, y=y
        )
    return deleted


Observation = apps.get_model("observations", "Observation")
ObservationSegment = apps.get_model("observations", "ObservationSegment")

# Layers used by the segment tiles view; must match id list used in the view
SEGMENT_LAYER_IDS = ("observation-segments",)


logger = logging.getLogger(__name__)


@receiver(post_save, sender=Observation)
def invalidate_segment_tiles_on_observation_change(sender=None, instance=None, **kwargs):
    """Invalidate segment vector tile cache when an observation changes.

    We invalidate tiles containing the observation location across relevant zoom levels.
    Segments are built from observations, so this is a safe heuristic and avoids computing line intersections.
    """
    try:
        if not instance or not instance.location:
            return
        lon = float(instance.location.x)
        lat = float(instance.location.y)
        tenant_id = str(instance.das_tenant_id)
        _invalidate_for_point(tenant_id=tenant_id, layer_ids=SEGMENT_LAYER_IDS, lon=lon, lat=lat)
    except Exception as exc:
        logger.error("Segment tile cache invalidation failed on Observation change: %s", exc, exc_info=True)


@receiver(post_save, sender=ObservationSegment)
def invalidate_segment_tiles_on_segment_change(sender=None, instance=None, **kwargs):
    """Invalidate segment vector tile cache when a segment changes.

    Invalidate tiles for both endpoints to improve coverage.
    """
    try:
        if not instance:
            return
        tenant_id = str(instance.das_tenant_id)
        a = instance.start_observation.location
        b = instance.end_observation.location
        if a:
            _invalidate_for_point(
                tenant_id=tenant_id,
                layer_ids=SEGMENT_LAYER_IDS,
                lon=float(a.x),
                lat=float(a.y),
            )
        if b:
            _invalidate_for_point(
                tenant_id=tenant_id,
                layer_ids=SEGMENT_LAYER_IDS,
                lon=float(b.x),
                lat=float(b.y),
            )
    except Exception as exc:
        logger.error("Segment tile cache invalidation failed on ObservationSegment change: %s", exc, exc_info=True)
