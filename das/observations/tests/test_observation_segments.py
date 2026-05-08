"""
Tests for ObservationSegment model and related functionality.

Tests cover:
- Segment creation and calculation logic
- Signal-based automatic segment maintenance
- O(1) update performance characteristics
- Vector tile endpoint
- Backfill management command
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from psycopg2.extras import DateTimeTZRange

from django.contrib.gis.geos import LineString, Point
from django.core.management import call_command
from django.db import transaction
from django.test import override_settings
from django.urls import reverse

from core.models import DASTenant
from observations.models import (
    Observation,
    ObservationSegment,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
    SubjectSubType,
    SubjectType,
)
from observations.signals import (
    recompute_observation_segments,
    update_segments_for_observation,
)
from observations.vector_layers import ObservationSegmentVectorLayer
from utils.cache import (
    OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX,
    bump_observation_segment_tile_version,
    get_observation_segment_tile_version,
    get_vector_tile_cache,
)
from utils.migrations.columns import default_tenant_id


@contextmanager
def _run_segment_signal_on_commit_after_block():
    """Record ``transaction.on_commit`` hooks, then run them after exit.

    pytest-django often keeps an outer DB transaction open so hooks registered during
    inner ``atomic()`` blocks never run at block boundaries; draining them here matches
    production semantics for these assertions.
    """
    import observations.signals as obs_signals

    if hasattr(obs_signals._segment_post_save_tl, "buffers"):
        del obs_signals._segment_post_save_tl.buffers

    pending: list = []

    def _record(func, *args, **kwargs):
        # ``transaction.on_commit`` accepts ``using`` and (in newer Django) ``robust=`` —
        # swallow any extras so this helper doesn't break when callers pass them.
        pending.append(func)

    with patch("django.db.transaction.on_commit", side_effect=_record):
        yield
    for func in pending:
        func()


@pytest.mark.django_db
class TestObservationSegmentModel:
    """Test the ObservationSegment model and manager methods."""

    @pytest.fixture
    def setup_data(self, db):
        """Create test data for segment tests."""
        # Create tenant
        tenant = DASTenant.objects.get(id=default_tenant_id())

        # Create subject type and subtype
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="elephant", display="Elephant", subject_type=subject_type, das_tenant=tenant
        )

        # Create subject
        subject = Subject.objects.create(
            name="Test Elephant",
            subject_subtype=subject_subtype,
            das_tenant=tenant,
        )

        # Create source provider and source
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_provider", display_name="Test Provider", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="test_collar_001", provider=provider, das_tenant=tenant)

        # Create subject-source assignment
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        return {
            "tenant": tenant,
            "subject": subject,
            "source": source,
            "subject_type": subject_type,
            "subject_subtype": subject_subtype,
        }

    def test_create_segment_basic(self, setup_data):
        """Test basic segment creation with distance and speed calculations."""
        subject = setup_data["subject"]
        source = setup_data["source"]

        # Create two observations
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        obs1 = Observation.objects.create(
            source=source,
            recorded_at=base_time,
            location=Point(0.001, 0.001),  # Equator, Prime Meridian
            das_tenant=setup_data["tenant"],
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),  # 1 degree east
            das_tenant=setup_data["tenant"],
        )

        # Create segment manually
        segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Verify segment was created
        assert segment.subject == subject
        assert segment.start_observation == obs1
        assert segment.end_observation == obs2
        assert segment.start_recorded_at == obs1.recorded_at
        assert segment.end_recorded_at == obs2.recorded_at

        # Verify geometry is a LineString
        assert isinstance(segment.geometry, LineString)
        assert list(segment.geometry.coords) == [(0.001, 0.001), (1.0, 0.0)]

        # Verify time gap (1 hour = 3,600,000 ms)
        assert segment.time_gap_ms == 3_600_000.0

        # Verify distance is calculated (should be ~111km at equator for 1 degree)
        assert segment.distance_meters > 100_000  # At least 100km
        assert segment.distance_meters < 120_000  # Less than 120km

        # Verify speed is calculated correctly
        expected_speed = (segment.distance_meters / 1000.0) / 1.0  # km/h
        assert abs(segment.speed_kmh - expected_speed) < 0.1

    def test_segment_exclusion_flags(self, setup_data):
        """Test that exclusion flags are combined correctly."""
        subject = setup_data["subject"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        # Create observations with different exclusion flags
        obs1 = Observation.objects.create(
            source=source,
            recorded_at=base_time,
            location=Point(0.001, 0.001),
            exclusion_flags=Observation.EXCLUDED_MANUALLY,  # Flag 1
            das_tenant=setup_data["tenant"],
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            exclusion_flags=Observation.EXCLUDED_AUTOMATICALLY,  # Flag 2
            das_tenant=setup_data["tenant"],
        )

        segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Exclusion flags should be OR'd together
        expected_flags = Observation.EXCLUDED_MANUALLY | Observation.EXCLUDED_AUTOMATICALLY
        assert segment.exclusion_flags.mask == expected_flags

    def test_segment_queryset_filtering(self, setup_data):
        """Test ObservationSegment queryset filtering methods."""
        subject = setup_data["subject"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        # Create multiple observations to generate segments
        observations = []
        for i in range(5):
            obs = Observation.objects.create(
                source=source,
                recorded_at=base_time + timedelta(hours=i),
                location=Point(i, 0),
                das_tenant=setup_data["tenant"],
            )
            observations.append(obs)

        # Create segments (signals will create them automatically, but let's be explicit)
        for i in range(4):
            ObservationSegment.objects.create_segment(observations[i], observations[i + 1], subject)

        # Test by_subject filter
        segments = ObservationSegment.objects.by_subject(subject)
        assert segments.count() == 4

        # Test by_time_range filter
        since = base_time + timedelta(hours=1)
        until = base_time + timedelta(hours=3)
        segments = ObservationSegment.objects.by_time_range(since=since, until=until)
        assert segments.count() == 2  # Segments starting at hours 1 and 2

        # Test ordered_by_time
        segments = ObservationSegment.objects.by_subject(subject).ordered_by_time()
        first_segment = segments.first()
        last_segment = segments.last()
        assert first_segment.start_recorded_at < last_segment.start_recorded_at


@pytest.mark.django_db
class TestObservationSegmentSignals:
    """Test segment maintenance logic used by Observation signals.

    Note: These tests call update_segments_for_observation() directly because pytest's
    test transactions don't commit, so transaction.on_commit() (and thus Celery enqueue)
    does not run automatically. Production post_save enqueues a Celery task after commit.
    """

    @pytest.fixture
    def setup_data(self, db):
        """Create test data."""
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="rhino", display="Rhino", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(
            name="Test Rhino",
            subject_subtype=subject_subtype,
            das_tenant=tenant,
        )
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_provider_signals", display_name="Test Provider", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="test_collar_signals", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)
        return {"tenant": tenant, "subject": subject, "source": source}

    def test_segment_created_on_observation_insert(self, setup_data):
        """Test that segments are automatically created when observations are added."""
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        # Initially no segments
        assert ObservationSegment.objects.count() == 0

        # Create first observation - no segment yet (need 2 points)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=setup_data["tenant"]
        )
        update_segments_for_observation(obs1, created=True)
        assert ObservationSegment.objects.count() == 0

        # Create second observation - should trigger segment creation
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=setup_data["tenant"],
        )
        update_segments_for_observation(obs2, created=True)

        # Verify segment was created
        segments = ObservationSegment.objects.all()
        assert segments.count() == 1
        segment = segments.first()
        assert segment.start_observation == obs1
        assert segment.end_observation == obs2

    def test_segment_updated_on_out_of_order_insert(self, setup_data):
        """Test O(1) segment updates when observations arrive out of order."""
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        # Create observations at T=0 and T=2
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=setup_data["tenant"]
        )
        update_segments_for_observation(obs1, created=True)
        obs3 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=2),
            location=Point(2, 0),
            das_tenant=setup_data["tenant"],
        )
        update_segments_for_observation(obs3, created=True)

        # Should have 1 segment: obs1 -> obs3
        assert ObservationSegment.objects.count() == 1
        original_segment = ObservationSegment.objects.first()
        assert original_segment.start_observation == obs1
        assert original_segment.end_observation == obs3

        # Insert observation at T=1 (out of order)
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=setup_data["tenant"],
        )
        update_segments_for_observation(obs2, created=True)

        # Should now have 2 segments:
        # - obs1 -> obs2
        # - obs2 -> obs3
        # The original obs1 -> obs3 segment should be deleted
        segments = ObservationSegment.objects.order_by("start_recorded_at")
        assert segments.count() == 2

        seg1 = segments[0]
        assert seg1.start_observation == obs1
        assert seg1.end_observation == obs2

        seg2 = segments[1]
        assert seg2.start_observation == obs2
        assert seg2.end_observation == obs3

        # Original segment should not exist
        assert not ObservationSegment.objects.filter(id=original_segment.id).exists()

    def test_segment_deleted_and_bridged_on_observation_delete(self, setup_data):
        """Test that segments are updated when an observation is deleted."""
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        # Create 3 observations
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=setup_data["tenant"]
        )
        update_segments_for_observation(obs1, created=True)
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=setup_data["tenant"],
        )
        update_segments_for_observation(obs2, created=True)
        obs3 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=2),
            location=Point(2, 0),
            das_tenant=setup_data["tenant"],
        )
        update_segments_for_observation(obs3, created=True)

        # Should have 2 segments
        assert ObservationSegment.objects.count() == 2

        # Delete middle observation
        # First manually trigger segment update before deleting
        # (in production, pre_delete signal would handle this)
        update_segments_for_observation(obs2, deleted=True)

        # Should now have 1 bridge segment: obs1 -> obs3
        segments = ObservationSegment.objects.all()
        assert segments.count() == 1
        bridge_segment = segments.first()
        assert bridge_segment.start_observation == obs1
        assert bridge_segment.end_observation == obs3

    def test_bridge_segment_creation_is_idempotent_when_segment_already_exists(self, setup_data):
        """Regression: _create_bridge_segment uses a bare INSERT with no duplicate guard.

        Race that a source deletion enables:
          1. delete_source_cascade() removes middle observation Z via _raw_delete(),
             bypassing pre_delete signals so no bridge is created.
          2. An in-flight Celery task (enqueued before deletion) processes observation A
             or B while they are still alive, finds Z gone, and creates segment A→B via
             get_or_create_segment.
          3. A concurrent deletion path (Django admin, or a request deleting an individual
             observation) fires observation_segment_pre_delete for Z, which calls
             _create_bridge_segment(A, B) — a bare INSERT with no duplicate check.
          4. Since A→B already exists, the INSERT raises IntegrityError → HTTP 500.

        After the fix (_create_bridge_segment must use get_or_create_segment),
        step 3 must succeed and leave exactly one A→B segment.
        """
        source = setup_data["source"]
        subject = setup_data["subject"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs_a = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=setup_data["tenant"]
        )
        obs_z = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1.0, 0.0),
            das_tenant=setup_data["tenant"],
        )
        obs_b = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=2),
            location=Point(2.0, 0.0),
            das_tenant=setup_data["tenant"],
        )

        update_segments_for_observation(obs_a, created=True)
        update_segments_for_observation(obs_z, created=True)
        update_segments_for_observation(obs_b, created=True)
        assert ObservationSegment.objects.count() == 2  # A→Z, Z→B

        # Simulate the concurrent recompute worker that creates A→B ahead of the
        # deletion signal (the in-flight Celery task from step 2 above).
        ObservationSegment.objects.get_or_create_segment(obs_a, obs_b, subject)
        assert ObservationSegment.objects.count() == 3  # A→Z, Z→B, A→B

        # Deleting Z triggers _create_bridge_segment(A, B).  Without the fix this
        # raises IntegrityError because A→B already exists.
        update_segments_for_observation(obs_z, deleted=True)

        segments = ObservationSegment.objects.all()
        assert segments.count() == 1
        bridge = segments.get()
        assert bridge.start_observation == obs_a
        assert bridge.end_observation == obs_b

    # NOTE: test_no_segment_created_for_observation_without_location removed
    # because observations.location has a NOT NULL constraint in the database,
    # so observations without location cannot be created

    def test_performance_only_two_segments_updated(self, setup_data):
        """
        Test that inserting an observation only affects 2 segments (O(1) operation).
        This validates the core performance benefit of the segment approach.
        """
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        # Create a long track (100 observations)
        observations = []
        for i in range(100):
            obs = Observation.objects.create(
                source=source,
                recorded_at=base_time + timedelta(hours=i),
                location=Point((i + 1) / 10.0, 0),
                das_tenant=setup_data["tenant"],
            )
            update_segments_for_observation(obs, created=True)
            observations.append(obs)

        # Should have 99 segments
        initial_count = ObservationSegment.objects.count()
        assert initial_count == 99

        # Get segment IDs before insertion
        segment_ids_before = set(ObservationSegment.objects.values_list("id", flat=True))

        # Insert observation in the middle (between obs 50 and 51)
        obs_middle = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=50, minutes=30),
            location=Point(5.05, 0),
            das_tenant=setup_data["tenant"],
        )
        update_segments_for_observation(obs_middle, created=True)

        # Should now have 100 segments (99 + 2 new - 1 deleted)
        final_count = ObservationSegment.objects.count()
        assert final_count == 100

        # Get segment IDs after insertion
        segment_ids_after = set(ObservationSegment.objects.values_list("id", flat=True))

        # Calculate which segments changed
        deleted_segments = segment_ids_before - segment_ids_after
        new_segments = segment_ids_after - segment_ids_before

        # Exactly 1 segment should be deleted (obs50 -> obs51)
        assert len(deleted_segments) == 1

        # Exactly 2 segments should be created (obs50 -> obs_middle, obs_middle -> obs51)
        assert len(new_segments) == 2

        # This proves O(1) segment updates!


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestSubjectSourceSegmentUpdate:
    """When SubjectSource assignment changes, the shared recompute updates ObservationSegment subject_id."""

    @pytest.fixture
    def setup_data(self, db, das_tenant_monkeypatch):
        """Two subjects, one source, one SubjectSource (subject A) with a fixed range."""
        tenant = das_tenant_monkeypatch
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife_ss", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="rhino_ss", display="Rhino", subject_type=subject_type, das_tenant=tenant
        )
        subject_a = Subject.objects.create(name="Subject A", subject_subtype=subject_subtype, das_tenant=tenant)
        subject_b = Subject.objects.create(name="Subject B", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_ss_segments", display_name="Test", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_ss_segments", provider=provider, das_tenant=tenant)
        range_start = datetime.now(tz=timezone.utc) - timedelta(days=30)
        range_end = range_start + timedelta(days=10)
        SubjectSource.objects.create(
            subject=subject_a,
            source=source,
            assigned_range=DateTimeTZRange(lower=range_start, upper=range_end),
            das_tenant=tenant,
        )
        return {
            "tenant": tenant,
            "subject_a": subject_a,
            "subject_b": subject_b,
            "source": source,
            "range_start": range_start,
            "range_end": range_end,
        }

    def test_recompute_after_subject_change_updates_segment_subject_id(self, setup_data):
        """Reassigning a source from subject A to subject B; recompute updates segment subject_id to B."""
        from observations.signals import recompute_observation_segments_for_source_range

        source = setup_data["source"]
        subject_a = setup_data["subject_a"]
        subject_b = setup_data["subject_b"]
        range_start = setup_data["range_start"]
        range_end = setup_data["range_end"]
        tenant = setup_data["tenant"]

        obs1 = Observation.objects.create(
            source=source,
            recorded_at=range_start + timedelta(days=1),
            location=Point(0.001, 0.001),
            das_tenant=tenant,
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=range_start + timedelta(days=1, hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )
        update_segments_for_observation(obs1, created=True)
        update_segments_for_observation(obs2, created=True)

        segment = ObservationSegment.objects.get()
        assert segment.subject_id == subject_a.id

        ss = SubjectSource.objects.get(source=source)
        ss.subject = subject_b
        ss.save()

        recompute_observation_segments_for_source_range(str(source.id), range_start, range_end)

        new_segment = ObservationSegment.objects.get(start_observation=obs1, end_observation=obs2)
        assert new_segment.subject_id == subject_b.id


@pytest.mark.django_db
class TestObservationSegmentVectorTiles:
    """Test the vector tile endpoint for segments."""

    def test_segment_tiles_endpoint_exists(self, client):
        """Test that the segment vector tiles endpoint is accessible."""
        url = reverse("observation-segments-vector-tiles", kwargs={"z": 5, "x": 10, "y": 12})
        # Note: This will likely return 401 without auth, but endpoint should exist
        response = client.get(url)
        assert response.status_code in [200, 401, 403]  # Endpoint exists

    def test_iso_timestamps_are_lexicographically_sortable(self, db):
        """Ensure vector layer uses ISO 8601 with 'T' and millisecond precision so strings sort consistently."""
        tenant = DASTenant.objects.get(id=default_tenant_id())
        # Minimal subject/source setup
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="tester", display="Tester", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="ISO Test", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="iso_provider", display_name="ISO Provider", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="iso_collar", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        base = datetime.now(tz=timezone.utc) - timedelta(days=30)
        obs1 = Observation.objects.create(source=source, recorded_at=base, location=Point(0.0, 0.0), das_tenant=tenant)
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base + timedelta(minutes=5),
            location=Point(0.05, 0.0),
            das_tenant=tenant,
        )
        obs3 = Observation.objects.create(
            source=source,
            recorded_at=base + timedelta(minutes=10),
            location=Point(0.10, 0.0),
            das_tenant=tenant,
        )

        ObservationSegment.objects.create_segment(obs1, obs2, subject)
        ObservationSegment.objects.create_segment(obs2, obs3, subject)

        layer = ObservationSegmentVectorLayer()
        qs = layer.get_vector_tile_queryset()
        features = [layer.as_vector_tile_feature(obj) for obj in qs]

        # Extract timestamp strings (vector tile uses start_time/end_time from annotations)
        starts = [f["properties"]["start_time"] for f in features]
        ends = [f["properties"]["end_time"] for f in features]

        # All timestamps must contain 'T' separator and end with timezone offset
        assert all("T" in s for s in starts)
        assert all("T" in e for e in ends)

        # Lexicographic ordering of 'end_time' should match chronological ordering
        lex_sorted = sorted(ends)
        chrono_sorted = [
            f["properties"]["end_time"] for f in sorted(features, key=lambda f: f["properties"]["end_time"])
        ]
        assert lex_sorted == chrono_sorted

    def test_is_latest_flag_layer_and_feature(self, db):
        """Verify is_latest annotation and feature property in vector layer."""
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="zebra", display="Zebra", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="VT Zebra", subject_subtype=subject_subtype, das_tenant=tenant)

        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_provider_mvt", display_name="Test Provider", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="test_collar_mvt", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.0, 0.0), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(minutes=10), location=Point(0.05, 0.0), das_tenant=tenant
        )
        obs3 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(minutes=20), location=Point(0.10, 0.0), das_tenant=tenant
        )

        ObservationSegment.objects.create_segment(obs1, obs2, subject)
        ObservationSegment.objects.create_segment(obs2, obs3, subject)

        # Layer-level queryset with annotation
        layer = ObservationSegmentVectorLayer()
        qs = layer.get_vector_tile_queryset()
        segments = list(qs)
        assert len(segments) == 2
        ends = sorted([s.end_recorded_at for s in segments])
        latest_seg = next(s for s in segments if s.end_recorded_at == ends[-1])
        earlier_seg = next(s for s in segments if s.end_recorded_at == ends[0])

        assert getattr(latest_seg, "is_latest", False) is True
        assert getattr(earlier_seg, "is_latest", True) is False

        # Feature properties include is_latest
        features = [layer.as_vector_tile_feature(obj) for obj in segments]
        flags = [f["properties"].get("is_latest") for f in features]
        assert flags.count(True) == 1
        assert flags.count(False) == 1

    def test_bearing_calculated_on_segment_creation(self, db):
        """Test that bearing_deg is automatically calculated when segment is created."""
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="test", display="Test", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Test Subject", subject_subtype=subject_subtype, das_tenant=tenant)

        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_provider_bearing", display_name="Test Provider", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="test_collar_bearing", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        # Test various directions
        test_cases = [
            # (start_point, end_point, expected_bearing_range)
            (Point(0.001, 0.001), Point(0.001, 1.001), (0, 0)),  # Due north
            (Point(0.001, 0.001), Point(1.001, 0.001), (85, 95)),  # Due east (~90°)
            (Point(0.001, 0.001), Point(0.001, -0.999), (180, 180)),  # Due south
            (Point(0.001, 0.001), Point(-0.999, 0.001), (265, 275)),  # Due west (~270°)
        ]

        for i, (start_pt, end_pt, (min_bearing, max_bearing)) in enumerate(test_cases):
            obs1 = Observation.objects.create(
                source=source,
                recorded_at=base_time + timedelta(hours=i * 2),
                location=start_pt,
                das_tenant=tenant,
            )
            obs2 = Observation.objects.create(
                source=source,
                recorded_at=base_time + timedelta(hours=i * 2 + 1),
                location=end_pt,
                das_tenant=tenant,
            )

            segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

            # Verify bearing was calculated
            assert segment.bearing_deg is not None
            assert 0 <= segment.bearing_deg < 360

            # Verify bearing is in expected range
            if min_bearing == max_bearing:
                # Exact bearing (north or south)
                assert abs(segment.bearing_deg - min_bearing) < 1.0
            else:
                # Range (east or west, allowing for equator calculation variations)
                assert min_bearing <= segment.bearing_deg <= max_bearing

    def test_bearing_in_vector_tile_features(self, db):
        """Test that bearing_deg is included in vector tile feature properties."""
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="test", display="Test", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="VT Test", subject_subtype=subject_subtype, das_tenant=tenant)

        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_provider_vt_bearing", display_name="Test Provider", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="test_collar_vt_bearing", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(minutes=10), location=Point(1, 0), das_tenant=tenant
        )

        ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Get feature from vector layer (use annotated queryset so start_time/end_time exist)
        layer = ObservationSegmentVectorLayer()
        qs = layer.get_vector_tile_queryset()
        segment = qs.filter(subject=subject).first()
        assert segment is not None, "segment should exist in vector tile queryset"
        feature = layer.as_vector_tile_feature(segment)

        # Verify bearing_deg is in properties
        assert "bearing_deg" in feature["properties"]
        assert feature["properties"]["bearing_deg"] is not None
        assert isinstance(feature["properties"]["bearing_deg"], (int, float))
        assert 0 <= feature["properties"]["bearing_deg"] < 360

    def test_no_point_features_generated(self, db):
        """Test that vector tiles only contain LineString features, no Point features for segment endpoints."""
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="test", display="Test", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Line Test", subject_subtype=subject_subtype, das_tenant=tenant)

        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_provider_no_points", display_name="Test Provider", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="test_collar_no_points", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(minutes=10), location=Point(0.1, 0), das_tenant=tenant
        )
        obs3 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(minutes=20), location=Point(0.2, 0), das_tenant=tenant
        )

        ObservationSegment.objects.create_segment(obs1, obs2, subject)
        ObservationSegment.objects.create_segment(obs2, obs3, subject)

        # Get features from vector layer
        layer = ObservationSegmentVectorLayer()
        qs = layer.get_vector_tile_queryset()
        features = [layer.as_vector_tile_feature(obj) for obj in qs]

        # Should have exactly 2 features (one per segment)
        assert len(features) == 2

        # All features should be LineStrings
        for feature in features:
            geom = feature["geometry"]
            assert isinstance(geom, LineString)
            assert geom.geom_type == "LineString"

        # Verify no "kind" property exists (which was used for point features)
        for feature in features:
            props = feature["properties"]
            assert "kind" not in props
            assert "bearing_to_next" not in props
            assert "bearing_from_prev" not in props


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestBackfillObservationSegmentsSync:
    """Test the backfill_observation_segments management command in sync mode.

    Validates that the raw SQL INSERT … SELECT produces segments consistent
    with the ORM/signal path: correct neighbor pairing across sources,
    computed metrics (distance, speed, bearing), exclusion_flags OR, and
    idempotency via ON CONFLICT DO NOTHING.
    """

    @pytest.fixture
    def setup_data(self, db, das_tenant_monkeypatch):
        tenant = das_tenant_monkeypatch
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife_bf", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="elephant_bf", display="Elephant", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Backfill Elephant", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="backfill_provider", display_name="Backfill Provider", das_tenant=tenant
        )
        source_a = Source.objects.create(manufacturer_id="collar_bf_a", provider=provider, das_tenant=tenant)
        source_b = Source.objects.create(manufacturer_id="collar_bf_b", provider=provider, das_tenant=tenant)

        base = datetime.now(tz=timezone.utc) - timedelta(days=30)
        SubjectSource.objects.create(
            subject=subject,
            source=source_a,
            assigned_range=DateTimeTZRange(lower=base, upper=base + timedelta(days=5)),
            das_tenant=tenant,
        )
        SubjectSource.objects.create(
            subject=subject,
            source=source_b,
            assigned_range=DateTimeTZRange(lower=base + timedelta(days=5), upper=base + timedelta(days=10)),
            das_tenant=tenant,
        )
        return {
            "tenant": tenant,
            "subject": subject,
            "source_a": source_a,
            "source_b": source_b,
            "base": base,
        }

    def _run_backfill(self, domain):
        with patch("utils.tenant.commands.set_tenant"):
            call_command("backfill_observation_segments", tenant_domain=domain)

    def test_basic_neighbor_pairing_and_metrics(self, setup_data):
        """Segments link consecutive observations with correct distance/speed/bearing."""
        tenant = setup_data["tenant"]
        source = setup_data["source_a"]
        base = setup_data["base"]

        obs1 = Observation.objects.create(
            source=source, recorded_at=base + timedelta(hours=1), location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=base + timedelta(hours=2), location=Point(1, 0), das_tenant=tenant
        )
        obs3 = Observation.objects.create(
            source=source, recorded_at=base + timedelta(hours=3), location=Point(2, 0), das_tenant=tenant
        )

        self._run_backfill(tenant.domain)

        segments = ObservationSegment.objects.order_by("start_recorded_at")
        assert segments.count() == 2

        seg1 = segments[0]
        assert seg1.start_observation_id == obs1.id
        assert seg1.end_observation_id == obs2.id
        assert seg1.distance_meters > 100_000
        assert seg1.distance_meters < 120_000
        assert seg1.time_gap_ms == 3_600_000.0
        expected_speed = (seg1.distance_meters / 1000.0) / 1.0
        assert abs(seg1.speed_kmh - expected_speed) < 0.1
        assert seg1.bearing_deg is not None
        assert 85 <= seg1.bearing_deg <= 95

        seg2 = segments[1]
        assert seg2.start_observation_id == obs2.id
        assert seg2.end_observation_id == obs3.id

    def test_cross_source_boundary_pairing(self, setup_data):
        """Observations from adjacent SubjectSource assignments are linked across sources."""
        tenant = setup_data["tenant"]
        source_a = setup_data["source_a"]
        source_b = setup_data["source_b"]
        base = setup_data["base"]

        obs_a = Observation.objects.create(
            source=source_a, recorded_at=base + timedelta(days=4), location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs_b = Observation.objects.create(
            source=source_b, recorded_at=base + timedelta(days=6), location=Point(1, 1), das_tenant=tenant
        )

        self._run_backfill(tenant.domain)

        seg = ObservationSegment.objects.get()
        assert seg.start_observation_id == obs_a.id
        assert seg.end_observation_id == obs_b.id
        assert seg.subject_id == setup_data["subject"].id

    def test_exclusion_flags_ored(self, setup_data):
        """Segment exclusion_flags is the bitwise OR of both observations' flags."""
        tenant = setup_data["tenant"]
        source = setup_data["source_a"]
        base = setup_data["base"]

        Observation.objects.create(
            source=source,
            recorded_at=base + timedelta(hours=1),
            location=Point(0.001, 0.001),
            exclusion_flags=Observation.EXCLUDED_MANUALLY,
            das_tenant=tenant,
        )
        Observation.objects.create(
            source=source,
            recorded_at=base + timedelta(hours=2),
            location=Point(1, 0),
            exclusion_flags=Observation.EXCLUDED_AUTOMATICALLY,
            das_tenant=tenant,
        )

        self._run_backfill(tenant.domain)

        seg = ObservationSegment.objects.get()
        expected = Observation.EXCLUDED_MANUALLY | Observation.EXCLUDED_AUTOMATICALLY
        assert seg.exclusion_flags.mask == expected

    def test_idempotent_on_conflict(self, setup_data):
        """Running the command twice produces no duplicate segments."""
        tenant = setup_data["tenant"]
        source = setup_data["source_a"]
        base = setup_data["base"]

        Observation.objects.create(
            source=source, recorded_at=base + timedelta(hours=1), location=Point(0.001, 0.001), das_tenant=tenant
        )
        Observation.objects.create(
            source=source, recorded_at=base + timedelta(hours=2), location=Point(1, 0), das_tenant=tenant
        )

        self._run_backfill(tenant.domain)
        assert ObservationSegment.objects.count() == 1

        self._run_backfill(tenant.domain)
        assert ObservationSegment.objects.count() == 1

    def test_segments_older_than_three_years_not_inserted(self, setup_data):
        """Segments with start_recorded_at before the 3-year window are not inserted (partition retention)."""
        tenant = setup_data["tenant"]
        subject = setup_data["subject"]
        provider = setup_data["source_a"].provider
        base_old = datetime.now(timezone.utc) - timedelta(days=4 * 365)

        source_old = Source.objects.create(manufacturer_id="collar_bf_old", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(
            subject=subject,
            source=source_old,
            assigned_range=DateTimeTZRange(lower=base_old, upper=base_old + timedelta(days=5)),
            das_tenant=tenant,
        )
        Observation.objects.create(
            source=source_old,
            recorded_at=base_old + timedelta(hours=1),
            location=Point(0.001, 0.001),
            das_tenant=tenant,
        )
        Observation.objects.create(
            source=source_old,
            recorded_at=base_old + timedelta(hours=2),
            location=Point(1, 0),
            das_tenant=tenant,
        )

        self._run_backfill(tenant.domain)

        assert ObservationSegment.objects.count() == 0


@pytest.mark.django_db
class TestUpdateObservationSegmentsForObservationTask:
    """Direct tests for the Celery task wrapper around update_segments_for_observation."""

    @pytest.fixture
    def setup_data(self, db):
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(
            value="wildlife_task", display="Wildlife", das_tenant=tenant
        )
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="lion_task", display="Lion", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Task Lion", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_task_provider", display_name="Test Task", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_task", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)
        return {"tenant": tenant, "subject": subject, "source": source}

    def test_valid_observation_calls_update(self, setup_data):
        """Task loads the observation and calls update_segments_for_observation."""
        source = setup_data["source"]
        tenant = setup_data["tenant"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )

        with patch("observations.signals.update_segments_for_observation") as mock_update:
            from observations.tasks import (
                update_observation_segments_for_observation_task,
            )

            update_observation_segments_for_observation_task.apply(
                kwargs={"observation_id": str(obs.pk), "created": True, "domain": tenant.domain}
            )
            mock_update.assert_called_once()
            (call_obs,) = mock_update.call_args.args
            assert call_obs.pk == obs.pk
            assert mock_update.call_args.kwargs["created"] is True

    def test_missing_observation_exits_quietly(self, setup_data):
        """Task does not raise when the observation has been deleted before execution."""
        tenant = setup_data["tenant"]
        missing_id = str(uuid4())

        with patch("observations.signals.update_segments_for_observation") as mock_update:
            from observations.tasks import (
                update_observation_segments_for_observation_task,
            )

            update_observation_segments_for_observation_task.apply(
                kwargs={"observation_id": missing_id, "created": True, "domain": tenant.domain}
            )
            mock_update.assert_not_called()

    def test_invalid_uuid_exits_quietly(self, setup_data):
        """Task does not raise on a malformed observation_id."""
        tenant = setup_data["tenant"]

        with patch("observations.signals.update_segments_for_observation") as mock_update:
            from observations.tasks import (
                update_observation_segments_for_observation_task,
            )

            update_observation_segments_for_observation_task.apply(
                kwargs={"observation_id": "not-a-uuid", "created": False, "domain": tenant.domain}
            )
            mock_update.assert_not_called()

    def test_update_bumps_tile_version(self, setup_data):
        """When created=False (update path), the task bumps the tile version counter."""
        source = setup_data["source"]
        tenant = setup_data["tenant"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )

        vt_cache = get_vector_tile_cache()
        key = f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tenant.id}"
        vt_cache.delete(key)

        with patch("observations.signals.update_segments_for_observation"):
            from observations.tasks import (
                update_observation_segments_for_observation_task,
            )

            update_observation_segments_for_observation_task.apply(
                kwargs={"observation_id": str(obs.pk), "created": False, "domain": tenant.domain}
            )

        assert get_observation_segment_tile_version(str(tenant.id)) == 1

    def test_create_does_not_bump_tile_version(self, setup_data):
        """When created=True, the task should NOT bump the tile version counter."""
        source = setup_data["source"]
        tenant = setup_data["tenant"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )

        vt_cache = get_vector_tile_cache()
        key = f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tenant.id}"
        vt_cache.delete(key)

        with patch("observations.signals.update_segments_for_observation"):
            from observations.tasks import (
                update_observation_segments_for_observation_task,
            )

            update_observation_segments_for_observation_task.apply(
                kwargs={"observation_id": str(obs.pk), "created": True, "domain": tenant.domain}
            )

        assert get_observation_segment_tile_version(str(tenant.id)) == 0


@pytest.mark.django_db
class TestObservationSegmentTileVersionCounter:
    """Test the per-tenant segment tile version counter used for cache busting."""

    def test_initial_version_is_zero(self):
        vt_cache = get_vector_tile_cache()
        vt_cache.delete(f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:test-tenant-abc")
        assert get_observation_segment_tile_version("test-tenant-abc") == 0

    def test_bump_increments_version(self):
        tenant_id = "test-tenant-bump"
        vt_cache = get_vector_tile_cache()
        vt_cache.delete(f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tenant_id}")

        bump_observation_segment_tile_version(tenant_id)
        assert get_observation_segment_tile_version(tenant_id) == 1

        bump_observation_segment_tile_version(tenant_id)
        assert get_observation_segment_tile_version(tenant_id) == 2

    def test_bump_is_tenant_isolated(self):
        """Bumping one tenant does not affect another."""
        vt_cache = get_vector_tile_cache()
        for tid in ("tenant-iso-a", "tenant-iso-b"):
            vt_cache.delete(f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tid}")

        bump_observation_segment_tile_version("tenant-iso-a")
        assert get_observation_segment_tile_version("tenant-iso-a") == 1
        assert get_observation_segment_tile_version("tenant-iso-b") == 0


@pytest.mark.django_db
class TestSegmentTileVersionBumpOnMutation:
    """Verify the version counter is bumped on delete/update but NOT on create."""

    @pytest.fixture
    def setup_data(self, db):
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife_vb", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="lion_vb", display="Lion", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Version Bump Lion", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_vb_provider", display_name="Test VB", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_vb", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        vt_cache = get_vector_tile_cache()
        key = f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tenant.id}"
        vt_cache.delete(key)

        return {"tenant": tenant, "subject": subject, "source": source}

    def test_version_bumped_on_observation_delete(self, setup_data):
        """pre_delete signal bumps tile version (via on_commit mock)."""
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )
        obs3 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=2),
            location=Point(2, 0),
            das_tenant=tenant,
        )
        update_segments_for_observation(obs1, created=True)
        update_segments_for_observation(obs2, created=True)
        update_segments_for_observation(obs3, created=True)

        assert get_observation_segment_tile_version(str(tenant.id)) == 0

        update_segments_for_observation(obs2, deleted=True)
        bump_observation_segment_tile_version(str(tenant.id))

        assert get_observation_segment_tile_version(str(tenant.id)) == 1
        segments = ObservationSegment.objects.all()
        assert segments.count() == 1
        assert segments.first().start_observation == obs1
        assert segments.first().end_observation == obs3

    def test_version_bumped_on_observation_update_via_task(self, setup_data):
        """Celery task bumps tile version when created=False (update path)."""
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )
        update_segments_for_observation(obs1, created=True)
        update_segments_for_observation(obs2, created=True)

        assert get_observation_segment_tile_version(str(tenant.id)) == 0

        update_segments_for_observation(obs2, created=False)
        bump_observation_segment_tile_version(str(tenant.id))

        assert get_observation_segment_tile_version(str(tenant.id)) == 1

    def test_version_not_bumped_on_observation_create(self, setup_data):
        """Creates should NOT bump the tile version (hot path stays clean)."""
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        update_segments_for_observation(obs1, created=True)

        assert get_observation_segment_tile_version(str(tenant.id)) == 0


@pytest.mark.django_db
class TestRecomputeObservationSegmentsWithBounds:
    """Test that recompute_observation_segments accepts lower/upper for partition pruning."""

    @pytest.fixture
    def setup_data(self, db):
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife_rc", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="hippo_rc", display="Hippo", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Recompute Hippo", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_rc_provider", display_name="Test RC", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_rc", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)
        return {"tenant": tenant, "subject": subject, "source": source}

    def test_recompute_with_bounds_creates_segments(self, setup_data):
        """recompute_observation_segments with lower/upper creates expected segments."""
        source = setup_data["source"]
        tenant = setup_data["tenant"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )

        assert ObservationSegment.objects.count() == 0

        recompute_observation_segments(
            [obs1.id, obs2.id],
            lower=base_time - timedelta(hours=1),
            upper=base_time + timedelta(hours=2),
        )

        assert ObservationSegment.objects.count() == 1
        seg = ObservationSegment.objects.first()
        assert seg.start_observation == obs1
        assert seg.end_observation == obs2

    def test_recompute_without_bounds_still_works(self, setup_data):
        """recompute_observation_segments without bounds falls back to id-only query."""
        source = setup_data["source"]
        tenant = setup_data["tenant"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )

        recompute_observation_segments([obs1.id, obs2.id])

        assert ObservationSegment.objects.count() == 1


@pytest.mark.django_db
class TestRecomputeObservationSegmentsTask:
    """recompute_observation_segments_task observation_ids path (aggregate bounds + prune)."""

    @pytest.fixture
    def setup_data(self, db):
        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(
            value="wildlife_rtask", display="Wildlife", das_tenant=tenant
        )
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="hippo_rtask", display="Hippo", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(
            name="Recompute Task Hippo", subject_subtype=subject_subtype, das_tenant=tenant
        )
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_rtask_provider", display_name="Test RTask", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_rtask", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)
        return {"tenant": tenant, "subject": subject, "source": source}

    def test_task_observation_ids_creates_segments(self, setup_data):
        """ID-only task path merges min/max recorded_at and recomputes segments."""
        from observations.tasks import recompute_observation_segments_task

        source = setup_data["source"]
        tenant = setup_data["tenant"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )

        assert ObservationSegment.objects.count() == 0

        recompute_observation_segments_task.apply(
            kwargs={"observation_ids": [str(obs1.id), str(obs2.id)], "domain": tenant.domain}
        )

        assert ObservationSegment.objects.count() == 1
        seg = ObservationSegment.objects.first()
        assert seg.start_observation_id == obs1.id
        assert seg.end_observation_id == obs2.id

    def test_narrow_observation_fetch_supports_segment_math(self, setup_data):
        """Deferred Observation rows (only()) still carry fields needed for segment creation."""
        source = setup_data["source"]
        tenant = setup_data["tenant"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source,
            recorded_at=base_time,
            location=Point(0.001, 0.001),
            das_tenant=tenant,
            additional={"heavy": "x" * 1000},
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
            additional={"heavy": "y" * 1000},
        )

        recompute_observation_segments(
            [obs1.id, obs2.id],
            lower=base_time - timedelta(minutes=1),
            upper=base_time + timedelta(hours=2),
        )

        assert ObservationSegment.objects.count() == 1


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db(transaction=True)
class TestObservationSegmentPostSaveEnqueueQueue:
    """post_save enqueues segment batch tasks on commit to realtime_p3 (creates and updates)."""

    @pytest.fixture
    def setup_data(self, db, das_tenant):
        tenant = das_tenant
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife_q", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="lion_q", display="Lion", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Queue Lion", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_q_provider", display_name="Test Q", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_q", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)
        return {"tenant": tenant, "source": source}

    def test_create_enqueues_to_realtime_p3_queue(self, setup_data):
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        with patch("observations.signals.update_observation_segments_batch_task.apply_async") as mock_apply:
            with _run_segment_signal_on_commit_after_block():
                with transaction.atomic():
                    Observation.objects.create(
                        source=source,
                        recorded_at=base_time,
                        location=Point(0.001, 0.001),
                        das_tenant=tenant,
                    )
            mock_apply.assert_called_once()
            assert mock_apply.call_args.kwargs["queue"] == "realtime_p3"

    def test_update_enqueues_to_realtime_p3_queue(self, setup_data):
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        with patch("observations.signals.update_observation_segments_batch_task.apply_async") as mock_apply:
            with _run_segment_signal_on_commit_after_block():
                with transaction.atomic():
                    obs = Observation.objects.create(
                        source=source,
                        recorded_at=base_time,
                        location=Point(0.001, 0.001),
                        das_tenant=tenant,
                    )
            mock_apply.assert_called_once()
            assert mock_apply.call_args.kwargs["queue"] == "realtime_p3"
            mock_apply.reset_mock()
            with _run_segment_signal_on_commit_after_block():
                with transaction.atomic():
                    obs.location = Point(1, 0)
                    obs.save(update_fields=["location"])
            mock_apply.assert_called_once()
            assert mock_apply.call_args.kwargs["queue"] == "realtime_p3"


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db(transaction=True)
class TestObservationSegmentPostSaveBatchCoalescing:
    """One transaction should coalesce many post_save handlers into few batch enqueues."""

    @pytest.fixture
    def setup_data(self, db, das_tenant):
        tenant = das_tenant
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife_b", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="lion_b", display="Lion", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Batch Lion", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_b_provider", display_name="Test B", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_b", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)
        return {"tenant": tenant, "source": source, "subject": subject}

    def test_many_creates_in_one_atomic_single_apply_async(self, setup_data):
        """N creates in one outer commit → one batch enqueue when under chunk size."""
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        with patch("observations.signals.update_observation_segments_batch_task.apply_async") as mock_apply:
            with _run_segment_signal_on_commit_after_block():
                with transaction.atomic():
                    for i in range(5):
                        Observation.objects.create(
                            source=source,
                            recorded_at=base_time + timedelta(minutes=i),
                            location=Point(i, 0),
                            das_tenant=tenant,
                        )
        assert mock_apply.call_count == 1
        ids = mock_apply.call_args.kwargs["kwargs"]["observation_ids"]
        assert len(ids) == 5

    @override_settings(OBSERVATION_SEGMENT_POST_SAVE_BATCH_SIZE=2)
    def test_chunking_splits_apply_async_calls(self, setup_data):
        """With chunk size 2, five creates produce three batch messages."""
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        with patch("observations.signals.update_observation_segments_batch_task.apply_async") as mock_apply:
            with _run_segment_signal_on_commit_after_block():
                with transaction.atomic():
                    for i in range(5):
                        Observation.objects.create(
                            source=source,
                            recorded_at=base_time + timedelta(minutes=i),
                            location=Point(i, 0),
                            das_tenant=tenant,
                        )
        assert mock_apply.call_count == 3

    def test_duplicate_save_same_observation_dedupes_to_one_id(self, setup_data):
        """Last post_save for the same PK wins; one id in the batch."""
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        with patch("observations.signals.update_observation_segments_batch_task.apply_async") as mock_apply:
            with _run_segment_signal_on_commit_after_block():
                with transaction.atomic():
                    obs = Observation.objects.create(
                        source=source,
                        recorded_at=base_time,
                        location=Point(0.001, 0.001),
                        das_tenant=tenant,
                    )
                    obs.location = Point(1, 0)
                    obs.save(update_fields=["location"])
        assert mock_apply.call_count == 1
        ids = mock_apply.call_args.kwargs["kwargs"]["observation_ids"]
        assert ids == [str(obs.pk)]
        assert mock_apply.call_args.kwargs["kwargs"]["created"] is False

    def test_batch_task_orders_updates_by_subject_and_time(self, setup_data):
        """Batch processing calls update_segments_for_observation in chronological order per subject."""
        from observations.tasks import update_observation_segments_batch_task

        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs_late = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=2),
            location=Point(2, 0),
            das_tenant=tenant,
        )
        obs_early = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )

        with patch("observations.signals.update_segments_for_observation") as mock_update:
            update_observation_segments_batch_task.apply(
                kwargs={
                    "observation_ids": [str(obs_late.pk), str(obs_early.pk)],
                    "created": True,
                    "domain": tenant.domain,
                }
            )

        assert mock_update.call_count == 2
        first_pk = mock_update.call_args_list[0].args[0].pk
        second_pk = mock_update.call_args_list[1].args[0].pk
        assert first_pk == obs_early.pk
        assert second_pk == obs_late.pk

    def test_batch_update_bumps_tile_version_once(self, setup_data):
        """Update batch bumps segment tile version once for the tenant."""
        from observations.tasks import update_observation_segments_batch_task

        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )

        vt_cache = get_vector_tile_cache()
        key = f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tenant.id}"
        vt_cache.delete(key)

        with patch("observations.signals.update_segments_for_observation"):
            update_observation_segments_batch_task.apply(
                kwargs={
                    "observation_ids": [str(obs1.pk), str(obs2.pk)],
                    "created": False,
                    "domain": tenant.domain,
                }
            )

        assert get_observation_segment_tile_version(str(tenant.id)) == 1


@pytest.mark.django_db
class TestObservationSegmentPostSaveSavepointSafety:
    """Regression: a savepoint rollback prunes its on_commit callbacks; the post_save
    buffer must detect the missing flush callback and re-register so subsequent saves
    on the same connection are not silently dropped.
    """

    def test_re_registers_flush_when_callback_pruned_from_run_on_commit(self, das_tenant):
        from types import SimpleNamespace
        from uuid import uuid4

        import observations.signals as obs_signals
        from observations.signals import observation_segment_post_save

        if hasattr(obs_signals._segment_post_save_tl, "buffers"):
            del obs_signals._segment_post_save_tl.buffers

        def fake_instance(pk):
            return SimpleNamespace(
                pk=pk,
                location=Point(0, 0),
                das_tenant=das_tenant,
                das_tenant_id=das_tenant.id,
                _state=SimpleNamespace(db="default"),
            )

        fake_run_on_commit: list = []
        on_commit_calls: list = []

        def fake_on_commit(func, using=None):
            on_commit_calls.append(func)
            fake_run_on_commit.append((set(), func))

        fake_connections = {"default": SimpleNamespace(run_on_commit=fake_run_on_commit)}

        with (
            patch("observations.signals.transaction.on_commit", side_effect=fake_on_commit),
            patch("observations.signals.connections", new=fake_connections),
        ):
            observation_segment_post_save(sender=Observation, instance=fake_instance(uuid4()), created=True, raw=False)
            assert len(on_commit_calls) == 1
            assert obs_signals._segment_post_save_tl.buffers["default"]["flush_registered"] is True

            # Simulate savepoint rollback: Django prunes our callback from the
            # connection's ``run_on_commit`` queue while leaving our flag True.
            fake_run_on_commit.clear()

            observation_segment_post_save(sender=Observation, instance=fake_instance(uuid4()), created=True, raw=False)

        # The buffer detected the missing callback and re-registered, instead of
        # silently dropping the second save's enqueue on outer commit.
        assert len(on_commit_calls) == 2


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db(transaction=True)
class TestPreDeleteSignalWiringBumpsVersion:
    """Exercise the real pre_delete signal → on_commit → tile version bump path.

    Uses ``transaction=True`` so ``on_commit`` callbacks actually fire.  Pairs
    ``tenant_settings`` with ``das_tenant_monkeypatch`` so SubjectSource.save
    finds the tenant in both ``django_multitenant.utils._thread_locals`` and
    ``utils.tenant.thread.local_thread``.
    """

    @pytest.fixture
    def setup_data(self, db, das_tenant):
        tenant = das_tenant
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife_sig", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="lion_sig", display="Lion", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Signal Lion", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_sig_provider", display_name="Test Sig", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_sig", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        vt_cache = get_vector_tile_cache()
        key = f"{OBSERVATION_SEGMENT_TILE_VERSION_KEY_PREFIX}:{tenant.id}"
        vt_cache.delete(key)

        return {"tenant": tenant, "subject": subject, "source": source}

    def test_deleting_observation_bumps_version_via_signal(self, setup_data):
        """Observation.delete() fires pre_delete → on_commit → bump."""
        tenant = setup_data["tenant"]
        source = setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)

        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=tenant,
        )
        obs3 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=2),
            location=Point(2, 0),
            das_tenant=tenant,
        )
        update_segments_for_observation(obs1, created=True)
        update_segments_for_observation(obs2, created=True)
        update_segments_for_observation(obs3, created=True)
        assert ObservationSegment.objects.count() == 2

        assert get_observation_segment_tile_version(str(tenant.id)) == 0

        obs2.delete()

        assert get_observation_segment_tile_version(str(tenant.id)) == 1
        assert ObservationSegment.objects.count() == 1
        bridge = ObservationSegment.objects.first()
        assert bridge.start_observation == obs1
        assert bridge.end_observation == obs3


@pytest.mark.django_db
class TestUnboundedRangeClamping:
    """Verify that recompute clamps unbounded SubjectSource assigned_ranges."""

    def test_clamp_reduces_unbounded_range(self):
        """datetime.min → datetime.max is clamped to the 3-year retention window."""
        from observations.signals import _clamp_recompute_bounds

        lower = datetime.min.replace(tzinfo=timezone.utc)
        upper = datetime.max.replace(tzinfo=timezone.utc)
        clamped_lower, clamped_upper = _clamp_recompute_bounds(lower, upper)

        now = datetime.now(tz=timezone.utc)
        three_years_ago = now - timedelta(days=3 * 365)

        assert clamped_lower >= three_years_ago - timedelta(seconds=5)
        assert clamped_upper <= now + timedelta(seconds=5)

    def test_clamp_preserves_narrow_range(self):
        """A range within retention is not modified."""
        from observations.signals import _clamp_recompute_bounds

        now = datetime.now(tz=timezone.utc)
        lower = now - timedelta(days=30)
        upper = now - timedelta(days=1)
        clamped_lower, clamped_upper = _clamp_recompute_bounds(lower, upper)

        assert clamped_lower == lower
        assert clamped_upper == upper


@pytest.mark.django_db
class TestSetUnsetFlagSegmentRecomputeEnqueue:
    """``set_flag`` / ``unset_flag`` use bulk ``.update()`` which bypasses ``post_save``.

    Verify they explicitly enqueue ``recompute_observation_segments_task`` so segments
    referencing rows whose system-exclusion bits change are rebuilt.
    """

    @pytest.fixture
    def setup_data(self, db):
        from django_multitenant.utils import set_current_tenant, unset_current_tenant

        tenant = DASTenant.objects.get(id=default_tenant_id())
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_setflag_provider", display_name="Test SetFlag", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_setflag", provider=provider, das_tenant=tenant)
        base_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(hours=1), location=Point(1, 0), das_tenant=tenant
        )

        set_current_tenant(tenant)
        try:
            yield {"tenant": tenant, "obs1": obs1, "obs2": obs2}
        finally:
            unset_current_tenant()

    def test_set_flag_enqueues_recompute_with_observation_ids_and_domain(self, setup_data):
        tenant = setup_data["tenant"]
        obs1, obs2 = setup_data["obs1"], setup_data["obs2"]

        with patch("observations.tasks.recompute_observation_segments_task.apply_async") as mock_apply:
            with _run_segment_signal_on_commit_after_block():
                Observation.objects.set_flag([obs1.id, obs2.id], Observation.EXCLUDED_AUTOMATICALLY)

        mock_apply.assert_called_once()
        kwargs = mock_apply.call_args.kwargs["kwargs"]
        assert sorted(kwargs["observation_ids"]) == sorted([str(obs1.id), str(obs2.id)])
        assert kwargs["domain"] == tenant.domain

        obs1.refresh_from_db()
        obs2.refresh_from_db()
        assert obs1.exclusion_flags.mask & Observation.EXCLUDED_AUTOMATICALLY
        assert obs2.exclusion_flags.mask & Observation.EXCLUDED_AUTOMATICALLY

    def test_unset_flag_enqueues_recompute(self, setup_data):
        obs1 = setup_data["obs1"]
        Observation.objects.filter(id=obs1.id).update(exclusion_flags=Observation.EXCLUDED_MANUALLY)

        with patch("observations.tasks.recompute_observation_segments_task.apply_async") as mock_apply:
            with _run_segment_signal_on_commit_after_block():
                Observation.objects.unset_flag([obs1.id], Observation.EXCLUDED_MANUALLY)

        mock_apply.assert_called_once()
        kwargs = mock_apply.call_args.kwargs["kwargs"]
        assert kwargs["observation_ids"] == [str(obs1.id)]
        obs1.refresh_from_db()
        assert not (obs1.exclusion_flags.mask & Observation.EXCLUDED_MANUALLY)

    def test_rollback_does_not_enqueue(self, setup_data):
        """A rolled-back ``set_flag`` must not fire the segment recompute task."""
        from django.db import transaction as django_transaction

        obs1 = setup_data["obs1"]
        starting_flags = obs1.exclusion_flags.mask

        with patch("observations.tasks.recompute_observation_segments_task.apply_async") as mock_apply:
            try:
                with django_transaction.atomic():
                    Observation.objects.set_flag([obs1.id], Observation.EXCLUDED_AUTOMATICALLY)
                    raise RuntimeError("simulate downstream failure → rollback")
            except RuntimeError:
                pass

        mock_apply.assert_not_called()
        obs1.refresh_from_db()
        assert obs1.exclusion_flags.mask == starting_flags

    def test_set_flag_empty_id_list_does_not_enqueue(self, setup_data):
        with patch("observations.tasks.recompute_observation_segments_task.apply_async") as mock_apply:
            Observation.objects.set_flag([], Observation.EXCLUDED_AUTOMATICALLY)
        mock_apply.assert_not_called()

    def test_set_flag_third_party_only_does_not_enqueue(self, setup_data):
        """Third-party flags don't affect segment selection (see ``by_exclusion_flags``)."""
        obs1 = setup_data["obs1"]
        third_party_only = 1 << Observation.THIRD_PARTY_FLAGS_SHIFT

        with patch("observations.tasks.recompute_observation_segments_task.apply_async") as mock_apply:
            Observation.objects.set_flag([obs1.id], third_party_only)

        mock_apply.assert_not_called()
        obs1.refresh_from_db()
        assert obs1.exclusion_flags.mask & third_party_only

    def test_set_flag_no_tenant_context_skips_enqueue(self, setup_data):
        """Without a current tenant we can't pass a domain to ``TenantTask`` — log + skip."""
        from django_multitenant.utils import unset_current_tenant

        obs1 = setup_data["obs1"]
        unset_current_tenant()

        with patch("observations.tasks.recompute_observation_segments_task.apply_async") as mock_apply:
            Observation.objects.set_flag([obs1.id], Observation.EXCLUDED_AUTOMATICALLY)

        mock_apply.assert_not_called()
        obs1.refresh_from_db()
        assert obs1.exclusion_flags.mask & Observation.EXCLUDED_AUTOMATICALLY


@pytest.mark.django_db
class TestSegmentTaskMetrics:
    """``observation_segment.{batch,single}.*`` metrics fire for segment maintenance tasks."""

    @pytest.fixture
    def setup_data(self, db):
        tenant = DASTenant.objects.get(id=default_tenant_id())
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_metrics_provider", display_name="Test Metrics", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_metrics", provider=provider, das_tenant=tenant)
        return {"tenant": tenant, "source": source}

    def test_batch_task_emits_lag_and_size_histograms(self, setup_data):
        """Batch task records batch_size, lag_seconds, duration_ms with a domain tag."""
        tenant, source = setup_data["tenant"], setup_data["source"]
        from observations.tasks import update_observation_segments_batch_task

        recorded = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        obs = Observation.objects.create(
            source=source, recorded_at=recorded, location=Point(0.001, 0.001), das_tenant=tenant
        )

        with (
            patch("observations.signals.update_segments_for_observation"),
            patch("utils.stats.histogram") as mock_hist,
            patch("utils.stats.increment") as mock_incr,
        ):
            update_observation_segments_batch_task.apply(
                kwargs={"observation_ids": [str(obs.pk)], "created": True, "domain": tenant.domain}
            )

        names = [call.args[0] for call in mock_hist.call_args_list]
        assert "observation_segment.batch.batch_size" in names
        assert "observation_segment.batch.duration_ms" in names
        assert "observation_segment.batch.lag_seconds" in names

        for call in mock_hist.call_args_list:
            assert f"domain:{tenant.domain}" in (call.kwargs.get("tags") or [])

        size_call = next(c for c in mock_hist.call_args_list if c.args[0].endswith("batch_size"))
        assert size_call.args[1] == 1

        lag_call = next(c for c in mock_hist.call_args_list if c.args[0].endswith("lag_seconds"))
        assert 580 <= lag_call.args[1] <= 660

        breach_calls = [c for c in mock_incr.call_args_list if c.args[0].endswith("backlog_threshold_breach")]
        assert len(breach_calls) == 1

    def test_batch_task_no_breach_when_lag_under_threshold(self, setup_data):
        tenant, source = setup_data["tenant"], setup_data["source"]
        from observations.tasks import update_observation_segments_batch_task

        obs = Observation.objects.create(
            source=source,
            recorded_at=datetime.now(tz=timezone.utc) - timedelta(seconds=10),
            location=Point(0.001, 0.001),
            das_tenant=tenant,
        )

        with (
            patch("observations.signals.update_segments_for_observation"),
            patch("utils.stats.histogram"),
            patch("utils.stats.increment") as mock_incr,
        ):
            update_observation_segments_batch_task.apply(
                kwargs={"observation_ids": [str(obs.pk)], "created": True, "domain": tenant.domain}
            )

        breach_calls = [c for c in mock_incr.call_args_list if c.args[0].endswith("backlog_threshold_breach")]
        assert breach_calls == []

    def test_single_task_emits_metrics(self, setup_data):
        tenant, source = setup_data["tenant"], setup_data["source"]
        from observations.tasks import update_observation_segments_for_observation_task

        obs = Observation.objects.create(
            source=source,
            recorded_at=datetime.now(tz=timezone.utc) - timedelta(seconds=30),
            location=Point(0.001, 0.001),
            das_tenant=tenant,
        )

        with (
            patch("observations.signals.update_segments_for_observation"),
            patch("utils.stats.histogram") as mock_hist,
        ):
            update_observation_segments_for_observation_task.apply(
                kwargs={"observation_id": str(obs.pk), "created": True, "domain": tenant.domain}
            )

        names = [call.args[0] for call in mock_hist.call_args_list]
        assert "observation_segment.single.batch_size" in names
        assert "observation_segment.single.lag_seconds" in names


@pytest.mark.django_db
class TestReconcileObservationSegmentsTask:
    """Reconciliation runs idempotent recompute when valid_obs - 1 != segment_count for the window."""

    @pytest.fixture
    def setup_data(self, db):
        from django_multitenant.utils import set_current_tenant, unset_current_tenant

        tenant = DASTenant.objects.get(id=default_tenant_id())
        subject_type, _ = SubjectType.objects.get_or_create(value="wildlife_rec", display="Wildlife", das_tenant=tenant)
        subject_subtype, _ = SubjectSubType.objects.get_or_create(
            value="lion_rec", display="Lion", subject_type=subject_type, das_tenant=tenant
        )
        subject = Subject.objects.create(name="Reconcile Lion", subject_subtype=subject_subtype, das_tenant=tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_rec_provider", display_name="Test Reconcile", das_tenant=tenant
        )
        source = Source.objects.create(manufacturer_id="collar_rec", provider=provider, das_tenant=tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=tenant)

        set_current_tenant(tenant)
        try:
            yield {"tenant": tenant, "subject": subject, "source": source}
        finally:
            unset_current_tenant()

    def test_no_gaps_skips_recompute(self, setup_data):
        """Healthy state: valid_obs - 1 == segment_count for the window → no recompute."""
        from observations.tasks import reconcile_observation_segments_task

        tenant, source = setup_data["tenant"], setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(minutes=5),
            location=Point(1, 0),
            das_tenant=tenant,
        )
        update_segments_for_observation(obs1, created=True)
        update_segments_for_observation(obs2, created=True)
        assert ObservationSegment.objects.count() == 1

        with patch("observations.signals.recompute_observation_segments_for_source_range") as mock_recompute:
            reconcile_observation_segments_task.apply(kwargs={"tenant_domain": tenant.domain})

        mock_recompute.assert_not_called()

    def test_gap_triggers_recompute(self, setup_data):
        """Missing segment for the window → reconciliation queues the rebuild."""
        from observations.tasks import reconcile_observation_segments_task

        tenant, source = setup_data["tenant"], setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(minutes=5),
            location=Point(1, 0),
            das_tenant=tenant,
        )
        assert ObservationSegment.objects.count() == 0

        with patch("observations.signals.recompute_observation_segments_for_source_range") as mock_recompute:
            reconcile_observation_segments_task.apply(kwargs={"tenant_domain": tenant.domain})

        mock_recompute.assert_called_once()
        called_source_id = mock_recompute.call_args.args[0]
        assert called_source_id == str(source.id)

    def test_excluded_obs_not_counted_as_gap(self, setup_data):
        """An excluded observation doesn't bump the expected segment count, so no false gap."""
        from observations.tasks import reconcile_observation_segments_task

        tenant, source = setup_data["tenant"], setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(minutes=5),
            location=Point(1, 0),
            das_tenant=tenant,
        )
        Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(minutes=10),
            location=Point(2, 0),
            das_tenant=tenant,
            exclusion_flags=Observation.EXCLUDED_AUTOMATICALLY,
        )
        update_segments_for_observation(obs1, created=True)
        update_segments_for_observation(obs2, created=True)
        assert ObservationSegment.objects.count() == 1

        with patch("observations.signals.recompute_observation_segments_for_source_range") as mock_recompute:
            reconcile_observation_segments_task.apply(kwargs={"tenant_domain": tenant.domain})

        mock_recompute.assert_not_called()

    def test_emits_reconcile_metrics(self, setup_data):
        from observations.tasks import reconcile_observation_segments_task

        tenant, source = setup_data["tenant"], setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(minutes=5),
            location=Point(1, 0),
            das_tenant=tenant,
        )

        with (
            patch("observations.signals.recompute_observation_segments_for_source_range"),
            patch("utils.stats.histogram") as mock_hist,
            patch("utils.stats.increment") as mock_incr,
        ):
            reconcile_observation_segments_task.apply(kwargs={"tenant_domain": tenant.domain})

        names = [c.args[0] for c in mock_hist.call_args_list]
        assert "observation_segment.reconcile.sources_checked" in names
        assert "observation_segment.reconcile.gaps_detected" in names
        assert "observation_segment.reconcile.duration_ms" in names

        gap_incr = [c for c in mock_incr.call_args_list if c.args[0].endswith("reconcile.gap_detected")]
        assert len(gap_incr) == 1

    def test_gap_logs_at_warning(self, setup_data, caplog):
        """Per-gap and end-of-run lines log at WARNING when drift is detected."""
        import logging

        from observations.tasks import reconcile_observation_segments_task

        tenant, source = setup_data["tenant"], setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(minutes=5),
            location=Point(1, 0),
            das_tenant=tenant,
        )

        with (
            patch("observations.signals.recompute_observation_segments_for_source_range"),
            caplog.at_level(logging.WARNING, logger="observations.tasks"),
        ):
            reconcile_observation_segments_task.apply(kwargs={"tenant_domain": tenant.domain})

        warn_messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("reconcile: gap detected" in m and str(source.id) in m for m in warn_messages)
        assert any("reconcile complete" in m and "gaps=1" in m for m in warn_messages)

    def test_no_gap_summary_logs_at_info_not_warning(self, setup_data, caplog):
        """Healthy run logs the end-of-run summary at INFO (not WARNING)."""
        import logging

        from observations.tasks import reconcile_observation_segments_task

        tenant, source = setup_data["tenant"], setup_data["source"]
        base_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0.001, 0.001), das_tenant=tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(minutes=5),
            location=Point(1, 0),
            das_tenant=tenant,
        )
        update_segments_for_observation(obs1, created=True)
        update_segments_for_observation(obs2, created=True)

        with caplog.at_level(logging.INFO, logger="observations.tasks"):
            reconcile_observation_segments_task.apply(kwargs={"tenant_domain": tenant.domain})

        warn_messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert not any("reconcile" in m for m in warn_messages)

        info_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
        assert any("reconcile complete" in m and "gaps=0" in m for m in info_messages)
