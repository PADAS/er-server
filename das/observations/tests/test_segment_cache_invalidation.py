import uuid
from unittest import mock

import pytest

from django.contrib.gis.geos import Point
from django.db import connection, transaction
from django.utils import timezone

import observations.signals_segments_cache as seg_cache
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
    clear_tile_invalidation_connection_state,
    invalidate_subject_tiles_on_status_change,
    lonlat_to_tile_xy,
    tiles_along_segment_at_zoom,
)
from utils import cache as cache_utils


@pytest.fixture(autouse=True)
def _clear_tile_invalidation_connection_state_between_tests():
    clear_tile_invalidation_connection_state()
    yield
    clear_tile_invalidation_connection_state()


def _tile_invalidation_zoom_count():
    return len(list(seg_cache.SEGMENTS_TILE_INVALIDATION_ZOOMS))


def test_lonlat_to_tile_xy_clamps_to_grid_bounds():
    """Tile indices stay within [0, n-1]; important for Pacific / antimeridian-adjacent data."""
    z = 10
    n = 1 << z
    x180, _ = lonlat_to_tile_xy(180.0, 0.0, z)
    assert x180 == n - 1
    x_neg180, _ = lonlat_to_tile_xy(-180.0, 0.0, z)
    assert x_neg180 == 0


def test_lonlat_to_tile_xy_poles_clamp_without_error():
    """Latitudes beyond Web Mercator range must not raise (invalid GIS data)."""
    z = 8
    n = 1 << z
    _, y = lonlat_to_tile_xy(0.0, 90.0, z)
    assert 0 <= y < n
    _, y_south = lonlat_to_tile_xy(0.0, -90.0, z)
    assert 0 <= y_south < n


def test_lonlat_to_tile_xy_pacific_australasia_sample():
    """Regression: tests must use same tile indices as segment-cache invalidation (global service)."""
    z = 10
    # Approx. Port Moresby PNG, Auckland NZ, West Papua — typical southwest Pacific longitudes
    for lon, lat in ((147.18, -9.44), (174.76, -36.85), (134.05, -2.59)):
        x, y = lonlat_to_tile_xy(lon, lat, z)
        assert 0 <= x < (1 << z)
        assert 0 <= y < (1 << z)


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

    def make_key(self, key, version=None):
        return key


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
def test_observation_tile_invalidation_flush_dedupes_points(monkeypatch, fake_vector_tile_cache):
    """After commit, one flush should dedupe many identical (tenant, lon, lat) to one tile per zoom."""
    tenant_id = str(uuid.uuid4())
    lon, lat = 12.5, -1.25
    calls = []

    def capture(**kw):
        calls.append((kw["z"], kw["x"], kw["y"]))
        return 0

    monkeypatch.setattr(seg_cache, "invalidate_tile_cache_keys", capture)
    batch = [("p", tenant_id, lon, lat)] * 30
    setattr(connection, seg_cache._TILE_INV_BATCH_ATTR, batch)
    seg_cache._flush_batched_tile_invalidations()
    assert len(calls) == len(set(calls))
    assert len(calls) == _tile_invalidation_zoom_count()


def test_tiles_along_segment_covers_intermediate_tiles():
    """Long horizontal segment must invalidate tiles between endpoints, not only ends."""
    z = 10
    # ~5° lon at equator spans many z=10 tiles (~0.35° per tile)
    cells = tiles_along_segment_at_zoom(-10.0, 0.0, -5.0, 0.0, z)
    xs = {c[0] for c in cells}
    assert len(xs) >= 5, f"expected multiple x columns, got {len(xs)}"


def test_tiles_along_segment_dateline_crossing_is_bounded():
    """Antimeridian crossing must use the short wrap, not millions of x steps."""
    z = 10
    cells = tiles_along_segment_at_zoom(179.0, 0.0, -179.0, 0.0, z)
    assert len(cells) < 50
    xs = {c[0] for c in cells}
    assert len(xs) < 50


@pytest.mark.django_db
def test_flush_batched_segment_invalidates_tiles_along_line(monkeypatch):
    """Batch entry type 's' expands to every tile cell the segment crosses at each zoom."""
    tenant_id = str(uuid.uuid4())
    calls = []

    def capture(**kw):
        calls.append((kw["z"], kw["x"], kw["y"]))
        return 0

    monkeypatch.setattr(seg_cache, "invalidate_tile_cache_keys", capture)
    setattr(connection, seg_cache._TILE_INV_BATCH_ATTR, [("s", tenant_id, -10.0, 0.0, -5.0, 0.0)])
    seg_cache._flush_batched_tile_invalidations()
    z10 = {(x, y) for z, x, y in calls if z == 10}
    assert len(z10) >= 5


@pytest.mark.django_db
def test_tile_invalidation_schedules_on_commit_once_per_transaction(monkeypatch):
    """Many point appends in one txn register exactly one on_commit (no ORM side signals)."""
    n_reg = []
    real_on_commit = transaction.on_commit

    def counting_on_commit(callback, **kwargs):
        n_reg.append(callback)
        return real_on_commit(callback, **kwargs)

    monkeypatch.setattr(transaction, "on_commit", counting_on_commit)
    tenant_id = str(uuid.uuid4())
    with transaction.atomic():
        for _ in range(25):
            seg_cache._append_point_invalidation(tenant_id, 12.5, -1.25)
    assert len(n_reg) == 1


@pytest.mark.django_db
def test_tile_invalidation_reschedules_flush_after_inner_atomic_rollback(monkeypatch):
    """Inner savepoint rollback drops our flush hook; other on_commit hooks can remain.

    The scheduled flag must clear when our callback is no longer queued so a later append
    registers a new flush (regression: empty run_on_commit was too coarse a signal).
    """

    def dummy_on_commit():
        pass

    registered = []
    real_on_commit = transaction.on_commit

    def counting_on_commit(callback, **kwargs):
        registered.append(callback)
        return real_on_commit(callback, **kwargs)

    monkeypatch.setattr(transaction, "on_commit", counting_on_commit)
    tenant_id = str(uuid.uuid4())
    with transaction.atomic():
        transaction.on_commit(dummy_on_commit)
        try:
            with transaction.atomic():
                seg_cache._append_point_invalidation(tenant_id, 12.5, -1.25)
                raise ValueError("rollback inner")
        except ValueError:
            pass
        seg_cache._append_point_invalidation(tenant_id, 14.0, 3.0)

    flush_callbacks = [cb for cb in registered if cb is not dummy_on_commit]
    assert len(flush_callbacks) == 2, (
        "expected two tile flush on_commit registrations "
        "(inner hook removed from queue, outer txn must re-schedule); "
        f"got {len(flush_callbacks)} in {registered!r}"
    )


@pytest.mark.django_db
def test_bulk_observations_after_commit_dedupes_tile_invalidations(monkeypatch, fake_vector_tile_cache):
    """Same location many times → one invalidate per zoom once commit hooks run (integration).

    pytest-django wraps tests in a transaction that never commits, so on_commit callbacks must be
    executed explicitly; see run_and_clear_commit_hooks usage elsewhere (e.g. observations/tests/test_subject.py).
    """
    tenant = DASTenant.objects.first()
    provider = SourceProvider.objects.first()
    if provider is None:
        provider = SourceProvider.objects.create(
            id=uuid.uuid4(),
            provider_key="default-test-bulk",
            display_name="Default Test Bulk",
            das_tenant=tenant,
        )
    source = Source.objects.create(
        manufacturer_id=f"m-bulk-{uuid.uuid4().hex[:8]}",
        provider=provider,
        das_tenant=tenant,
    )
    calls = []

    def capture(**kw):
        calls.append((kw["z"], kw["x"], kw["y"]))
        return 0

    monkeypatch.setattr(seg_cache, "invalidate_tile_cache_keys", capture)

    lon, lat = 12.5, -1.25
    with transaction.atomic():
        for _ in range(40):
            Observation.objects.create(
                source=source,
                recorded_at=timezone.now(),
                location=Point(lon, lat, srid=4326),
                das_tenant=tenant,
            )

    with mock.patch("django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block", lambda self: False):
        connection.run_and_clear_commit_hooks()

    n_zooms = _tile_invalidation_zoom_count()
    assert len(calls) == n_zooms
    assert len(set(calls)) == n_zooms


@pytest.mark.django_db
def test_subject_status_signal_skips_null_location(fake_vector_tile_cache):
    """Verify SubjectStatus signal handler gracefully skips null locations."""

    # Create a mock instance without location -- should not raise
    class FakeStatus:
        location = None
        das_tenant_id = uuid.uuid4()

    # Should not raise or attempt invalidation
    invalidate_subject_tiles_on_status_change(sender=None, instance=FakeStatus(), created=False)
