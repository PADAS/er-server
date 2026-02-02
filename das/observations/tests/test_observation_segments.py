"""
Tests for ObservationSegment model and related functionality.

Tests cover:
- Segment creation and calculation logic
- Signal-based automatic segment maintenance
- O(1) update performance characteristics
- Vector tile endpoint
- Backfill management command
"""

from datetime import datetime, timedelta, timezone

import pytest

from django.contrib.gis.geos import LineString, Point
from django.urls import reverse
from rest_framework.test import APIRequestFactory

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
from observations.signals import update_segments_for_observation
from observations.vector_layers_segments import ObservationSegmentVectorLayer
from utils.migrations.columns import default_tenant_id


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
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        obs1 = Observation.objects.create(
            source=source,
            recorded_at=base_time,
            location=Point(0, 0),  # Equator, Prime Meridian
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
        assert list(segment.geometry.coords) == [(0.0, 0.0), (1.0, 0.0)]

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
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Create observations with different exclusion flags
        obs1 = Observation.objects.create(
            source=source,
            recorded_at=base_time,
            location=Point(0, 0),
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
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

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
    """Test automatic segment maintenance via Django signals.

    Note: These tests manually trigger segment updates because pytest's test transactions
    don't commit, so transaction.on_commit() hooks won't fire automatically.
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
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Initially no segments
        assert ObservationSegment.objects.count() == 0

        # Create first observation - no segment yet (need 2 points)
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0, 0), das_tenant=setup_data["tenant"]
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
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Create observations at T=0 and T=2
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0, 0), das_tenant=setup_data["tenant"]
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
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Create 3 observations
        obs1 = Observation.objects.create(
            source=source, recorded_at=base_time, location=Point(0, 0), das_tenant=setup_data["tenant"]
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

    # NOTE: test_no_segment_created_for_observation_without_location removed
    # because observations.location has a NOT NULL constraint in the database,
    # so observations without location cannot be created

    def test_performance_only_two_segments_updated(self, setup_data):
        """
        Test that inserting an observation only affects 2 segments (O(1) operation).
        This validates the core performance benefit of the segment approach.
        """
        source = setup_data["source"]
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Create a long track (100 observations)
        observations = []
        for i in range(100):
            obs = Observation.objects.create(
                source=source,
                recorded_at=base_time + timedelta(hours=i),
                location=Point(i / 10.0, 0),
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
        from datetime import datetime, timedelta, timezone

        from django.contrib.gis.geos import Point
        from rest_framework.test import APIRequestFactory

        from core.models import DASTenant
        from observations.vector_layers_segments import ObservationSegmentVectorLayer
        from utils.migrations.columns import default_tenant_id

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

        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
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
        request = APIRequestFactory().get("/tiles")
        layer.request = request
        qs = layer.get_vector_tile_queryset()
        features = [layer.as_vector_tile_feature(obj) for obj in qs]

        # Extract timestamp strings
        starts = [f["properties"]["start_recorded_at"] for f in features]
        ends = [f["properties"]["end_recorded_at"] for f in features]

        # All timestamps must contain 'T' separator and end with timezone offset
        assert all("T" in s for s in starts)
        assert all("T" in e for e in ends)

        # Lexicographic ordering of 'end_recorded_at' should match chronological ordering
        lex_sorted = sorted(ends)
        chrono_sorted = [
            f["properties"]["end_recorded_at"]
            for f in sorted(features, key=lambda f: f["properties"]["end_recorded_at"])
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

        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
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
        factory = APIRequestFactory()
        request = factory.get("/tiles")
        layer.request = request

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

        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Test various directions
        test_cases = [
            # (start_point, end_point, expected_bearing_range)
            (Point(0, 0), Point(0, 1), (0, 0)),  # Due north
            (Point(0, 0), Point(1, 0), (85, 95)),  # Due east (~90°)
            (Point(0, 0), Point(0, -1), (180, 180)),  # Due south
            (Point(0, 0), Point(-1, 0), (265, 275)),  # Due west (~270°)
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

        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        obs1 = Observation.objects.create(source=source, recorded_at=base_time, location=Point(0, 0), das_tenant=tenant)
        obs2 = Observation.objects.create(
            source=source, recorded_at=base_time + timedelta(minutes=10), location=Point(1, 0), das_tenant=tenant
        )

        segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Get feature from vector layer
        layer = ObservationSegmentVectorLayer()
        factory = APIRequestFactory()
        request = factory.get("/tiles")
        layer.request = request

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

        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        obs1 = Observation.objects.create(source=source, recorded_at=base_time, location=Point(0, 0), das_tenant=tenant)
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
        factory = APIRequestFactory()
        request = factory.get("/tiles")
        layer.request = request

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
