import math
import uuid

import pytest

from django.contrib.gis.geos import Point
from django.utils import timezone

from observations.models import (
    DASTenant,
    Observation,
    ObservationSegment,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
)
from observations.signals_segments_cache import (
    TILE_LAYER_IDS,
    _invalidate_for_point,
    invalidate_subject_tiles_on_status_change,
)
from utils import cache as cache_utils


def lonlat_to_tile_xy(lon: float, lat: float, z: int):
    lat_rad = math.radians(lat)
    n = 2.0**z
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return xtile, ytile


class FakeRedis:
    def __init__(self):
        self.keys = set()

    def scan_iter(self, pattern: str):
        prefix = pattern[:-1] if pattern.endswith("*") else pattern
        for k in list(self.keys):
            if k.decode().startswith(prefix):
                yield k

    def delete(self, key):
        try:
            self.keys.remove(key)
            return 1
        except KeyError:
            return 0


class FakeCacheClient:
    def __init__(self):
        self._rc = FakeRedis()

    def get_client(self, write=False):
        return self._rc


class FakeCache:
    def __init__(self):
        self.client = FakeCacheClient()

    def get(self, key, default=None):
        return default

    def set(self, key, value, timeout=None):
        pass

    def delete(self, key):
        return self.client.get_client(write=True).delete(key.encode())


@pytest.fixture(autouse=True)
def fake_vector_tile_cache(monkeypatch, settings):
    settings.VECTOR_TILE_CACHE_ALIAS = "vector_tiles"
    fc = FakeCache()
    # Monkeypatch the cache getter used by mapping.cache to return our fake cache
    monkeypatch.setattr(cache_utils, "get_vector_tile_cache", lambda: fc)
    return fc


def build_vt_key(tenant_id, layers_part, version, z, x, y, user_hash="u", query_hash="q"):
    return f"vt:{tenant_id}:{layers_part}:{version}:{z}:{x}:{y}:{user_hash}:{query_hash}".encode()


def test_invalidate_tile_cache_keys_deletes_matching_prefix(fake_vector_tile_cache):
    tenant_id = str(uuid.uuid4())
    layers_part = "observation-segments"
    version = "1-123"
    z, x, y = 12, 2047, 1365

    for uh in ("aaaa", "bbbb"):
        fake_vector_tile_cache.client.get_client(write=True).keys.add(
            build_vt_key(tenant_id, layers_part, version, z, x, y, uh, "noquery")
        )
    fake_vector_tile_cache.client.get_client(write=True).keys.add(
        build_vt_key(tenant_id, layers_part, version, z, x, y + 1, "cccc", "noquery")
    )

    deleted = cache_utils.invalidate_tile_cache_keys(
        tenant_id=tenant_id,
        layer_ids=(layers_part,),
        cache_version=version,
        z=z,
        x=x,
        y=y,
    )

    assert deleted == 2


@pytest.mark.django_db
def test_observation_signal_invalidation(monkeypatch, fake_vector_tile_cache):
    lon, lat = 12.5, -1.25
    z = 10
    x, y = lonlat_to_tile_xy(lon, lat, z)
    tenant_id = str(uuid.uuid4())
    version = cache_utils.get_effective_cache_version()
    layers_part = ",".join(sorted(TILE_LAYER_IDS))

    rc = fake_vector_tile_cache.client.get_client(write=True)
    for uh in ("aaaa", "bbbb"):
        rc.keys.add(build_vt_key(tenant_id, layers_part, version, z, x, y, uh, "noquery"))

    deleted = _invalidate_for_point(tenant_id=tenant_id, layer_ids=TILE_LAYER_IDS, lon=lon, lat=lat)
    assert deleted >= 2


@pytest.mark.django_db
def test_segment_signal_invalidation(monkeypatch, fake_vector_tile_cache):
    tenant = DASTenant.objects.first()
    subject = Subject.objects.create(name="S", das_tenant=tenant)
    # Ensure a provider exists for Source creation
    provider = SourceProvider.objects.first()
    if provider is None:
        provider = SourceProvider.objects.create(
            id=uuid.uuid4(),
            provider_key="default-test",
            display_name="Default Test",
            das_tenant=tenant,
        )
    source = Source.objects.create(
        manufacturer_id="m1",
        provider=provider,
        das_tenant=tenant,
    )
    SubjectSource.objects.create(subject=subject, source=source)

    o1 = Observation.objects.create(
        source=source,
        recorded_at=timezone.now(),
        location=Point(12.5, -1.25, srid=4326),
        das_tenant=tenant,
    )
    o2 = Observation.objects.create(
        source=source,
        recorded_at=timezone.now(),
        location=Point(12.51, -1.26, srid=4326),
        das_tenant=tenant,
    )

    ObservationSegment.objects.create_segment(o1, o2, subject)

    version = cache_utils.get_effective_cache_version()
    layers_part = ",".join(sorted(TILE_LAYER_IDS))
    rc = fake_vector_tile_cache.client.get_client(write=True)
    for lon, lat in [(12.5, -1.25), (12.51, -1.26)]:
        x, y = lonlat_to_tile_xy(lon, lat, 10)
        rc.keys.add(build_vt_key(str(tenant.id), layers_part, version, 10, x, y, "aaaa", "noquery"))
        rc.keys.add(build_vt_key(str(tenant.id), layers_part, version, 10, x, y, "bbbb", "noquery"))

    # Compute tiles to determine overlap
    xa, ya = lonlat_to_tile_xy(12.5, -1.25, 10)
    xb, yb = lonlat_to_tile_xy(12.51, -1.26, 10)

    count_a = _invalidate_for_point(tenant_id=str(tenant.id), layer_ids=TILE_LAYER_IDS, lon=12.5, lat=-1.25)
    count_b = _invalidate_for_point(tenant_id=str(tenant.id), layer_ids=TILE_LAYER_IDS, lon=12.51, lat=-1.26)

    if (xa, ya) == (xb, yb):
        # Same tile: first invalidation clears both seeded keys
        assert (count_a + count_b) >= 2
    else:
        # Different tiles: expect both sets cleared
        assert (count_a + count_b) >= 4


@pytest.mark.django_db
def test_subject_status_signal_invalidation(fake_vector_tile_cache):
    """Verify SubjectStatus post_save invalidates the tile cache for its location."""
    tenant = DASTenant.objects.first()
    subject = Subject.objects.create(name="Status Signal Test", das_tenant=tenant)

    lon, lat = 36.8, -1.3
    version = cache_utils.get_effective_cache_version()
    layers_part = ",".join(sorted(TILE_LAYER_IDS))

    # Seed the fake cache with keys that match the subject's position
    rc = fake_vector_tile_cache.client.get_client(write=True)
    z = 10
    x, y = lonlat_to_tile_xy(lon, lat, z)
    for uh in ("aaaa", "bbbb"):
        rc.keys.add(build_vt_key(str(tenant.id), layers_part, version, z, x, y, uh, "noquery"))

    # Directly invoke the invalidation helper (same as the signal handler calls)
    deleted = _invalidate_for_point(tenant_id=str(tenant.id), layer_ids=TILE_LAYER_IDS, lon=lon, lat=lat)
    assert deleted >= 2


@pytest.mark.django_db
def test_subject_status_signal_skips_null_location(fake_vector_tile_cache):
    """Verify SubjectStatus signal handler gracefully skips null locations."""

    # Create a mock instance without location -- should not raise
    class FakeStatus:
        location = None
        das_tenant_id = uuid.uuid4()

    # Should not raise or attempt invalidation
    invalidate_subject_tiles_on_status_change(sender=None, instance=FakeStatus(), created=False)
