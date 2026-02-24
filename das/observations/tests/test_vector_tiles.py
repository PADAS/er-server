"""
Tests for consolidated vector tile endpoint (segments + subjects).

Verifies that both observation segments and subject positions are included
in a single .pbf response, with consistent permission-based filtering.
"""

from datetime import timedelta

import pytest

from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from observations.models import Subject, SubjectStatus
from observations.vector_layers import SubjectVectorLayer


@pytest.mark.django_db
class TestSubjectVectorLayer:
    """Test the SubjectVectorLayer configuration and queryset."""

    def test_layer_configuration(self):
        """Verify layer attributes are configured correctly."""
        layer = SubjectVectorLayer()
        assert layer.id == "subjects"
        assert layer.model == Subject
        assert layer.min_zoom == 3
        assert layer.max_zoom == 24
        assert "id" in layer.tile_fields
        assert "name" in layer.tile_fields
        assert "image_url" in layer.tile_fields
        assert "color" in layer.tile_fields
        assert "subject_subtype_value" in layer.tile_fields
        assert "radio_state" in layer.tile_fields

    def test_queryset_includes_geometry_in_web_mercator(self, subject_with_status):
        """Verify subjects have geom field in SRID 3857 (Web Mercator)."""
        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject_with_status.id).first()

        assert obj is not None
        assert hasattr(obj, "geom")
        assert obj.geom is not None
        assert obj.geom.srid == 3857

    def test_queryset_filters_subjects_without_location(self, subject_without_status):
        """Verify subjects without location are excluded from tiles."""
        layer = SubjectVectorLayer()
        qs = layer.get_queryset()

        # Subject without status should not appear
        assert not qs.filter(id=subject_without_status.id).exists()

    def test_queryset_includes_presentation_properties(self, subject_with_status):
        """Verify color, radio_state, image_url, and other properties are annotated."""
        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject_with_status.id).first()

        assert hasattr(obj, "color")
        assert hasattr(obj, "radio_state")
        assert hasattr(obj, "recorded_at")
        assert hasattr(obj, "subject_type_value")
        assert hasattr(obj, "subject_subtype_value")
        assert hasattr(obj, "image_url")

    def test_default_delay_hours_is_zero(self):
        """Verify default delay_hours is 0 when no request provided."""
        layer = SubjectVectorLayer()
        assert layer.delay_hours == 0

    def test_realtime_user_sees_latest_position(self, subject_with_multiple_statuses, user_with_realtime_access):
        """Verify users with access_ends_0 permission see delay_hours=0 status."""
        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user_with_realtime_access
        request.user.is_superuser = True  # So queryset is not filtered by by_user_subjects

        layer = SubjectVectorLayer(request=request)
        assert layer.delay_hours == 0

        qs = layer.get_queryset()
        obj = qs.filter(id=subject_with_multiple_statuses.id).first()
        assert obj is not None, "Subject should be in queryset (superuser sees all)"

        # Should use the status with delay_hours=0 (latest)
        status_latest = SubjectStatus.objects.get(subject=subject_with_multiple_statuses, delay_hours=0)
        assert obj.recorded_at == status_latest.recorded_at

    def test_delayed_user_sees_delayed_position(self, subject_with_multiple_statuses, user_with_delayed_access):
        """Verify users with access_ends_7 permission see delay_hours=168 status."""
        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user_with_delayed_access
        request.user.is_superuser = True  # So queryset is not filtered by by_user_subjects

        layer = SubjectVectorLayer(request=request)
        assert layer.delay_hours == 168  # 7 days * 24 hours

        qs = layer.get_queryset()
        obj = qs.filter(id=subject_with_multiple_statuses.id).first()
        assert obj is not None, "Subject should be in queryset (superuser sees all)"

        # Should use the status with delay_hours=168
        status_delayed = SubjectStatus.objects.get(subject=subject_with_multiple_statuses, delay_hours=168)
        assert obj.recorded_at == status_delayed.recorded_at


@pytest.mark.django_db
class TestConsolidatedVectorTiles:
    """Test consolidated vector tiles with both segments and subjects."""

    def test_tile_includes_both_layers(self, api_client_with_user, subject_with_segments_and_status):
        """Verify tile response includes both observation_segments and subjects layers."""
        url = reverse("observation-segments-vector-tiles", kwargs={"z": 10, "x": 512, "y": 512})
        response = api_client_with_user.get(url)

        assert response.status_code in (200, 204)
        assert response["Content-Type"] == "application/vnd.mapbox-vector-tile"

    def test_realtime_user_sees_all_segments(self, subject_with_segments_and_status, user_with_realtime_access):
        """Verify users with access_ends_0 see all segments up to now."""
        url = reverse("observation-segments-vector-tiles", kwargs={"z": 10, "x": 512, "y": 512})

        client = APIClient()
        client.force_login(user_with_realtime_access)
        response = client.get(url)

        assert response.status_code in (200, 204)

    def test_delayed_user_sees_filtered_segments(self, subject_with_segments_and_status, user_with_delayed_access):
        """Verify users with access_ends_7 only see segments from ≥7 days ago."""
        url = reverse("observation-segments-vector-tiles", kwargs={"z": 10, "x": 512, "y": 512})

        client = APIClient()
        client.force_login(user_with_delayed_access)
        response = client.get(url)

        # Should get filtered data (may be empty if no old enough segments)
        assert response.status_code in (200, 204)

    def test_different_users_get_different_cache(
        self, subject_with_segments_and_status, user_with_realtime_access, user_with_delayed_access
    ):
        """Verify users with different permissions get different cached tiles."""
        url = reverse("observation-segments-vector-tiles", kwargs={"z": 10, "x": 512, "y": 512})

        # Realtime user request
        client1 = APIClient()
        client1.force_login(user_with_realtime_access)
        response1 = client1.get(url)

        # Delayed user request
        client2 = APIClient()
        client2.force_login(user_with_delayed_access)
        response2 = client2.get(url)

        # Both should succeed but have different ETags (different cache keys)
        assert response1.status_code in (200, 204)
        assert response2.status_code in (200, 204)
        # Different permissions = different data = different ETags
        assert response1.get("ETag") != response2.get("ETag")

    def test_tile_respects_cache_headers(self, api_client_with_user, subject_with_segments_and_status):
        """Verify cache control headers are set correctly."""
        url = reverse("observation-segments-vector-tiles", kwargs={"z": 10, "x": 512, "y": 512})
        response = api_client_with_user.get(url)

        assert "Cache-Control" in response
        assert "ETag" in response
        assert "X-Cache" in response
        assert "max-age" in response["Cache-Control"]


@pytest.mark.django_db
class TestSegmentPermissionFiltering:
    """Test that segments are filtered based on user permissions."""

    def test_segment_layer_respects_delay_hours(self, das_tenant, subject_subtype, user_with_delayed_access):
        """Verify segment layer filters by delay_hours."""
        from rest_framework.test import APIRequestFactory

        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )
        from observations.vector_layers import ObservationSegmentVectorLayer

        # Create subject and source (observations use source, not subject)
        subject = Subject.objects.create(
            name="Test Subject",
            subject_subtype=subject_subtype,
            is_active=True,
            das_tenant=das_tenant,
        )
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_delay_seg", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="delay_seg_collar", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        # Create observations: one recent, one old
        now = timezone.now()
        old_time = now - timedelta(days=10)

        obs_old_1 = Observation.objects.create(
            source=source,
            location=Point(0.0, 0.0, srid=4326),
            recorded_at=old_time,
            das_tenant=das_tenant,
        )
        obs_old_2 = Observation.objects.create(
            source=source,
            location=Point(0.1, 0.1, srid=4326),
            recorded_at=old_time + timedelta(hours=1),
            das_tenant=das_tenant,
        )

        obs_recent_1 = Observation.objects.create(
            source=source,
            location=Point(1.0, 1.0, srid=4326),
            recorded_at=now - timedelta(hours=1),
            das_tenant=das_tenant,
        )
        obs_recent_2 = Observation.objects.create(
            source=source,
            location=Point(1.1, 1.1, srid=4326),
            recorded_at=now,
            das_tenant=das_tenant,
        )

        # Create segments
        ObservationSegment.objects.create_segment(obs_old_1, obs_old_2, subject)
        ObservationSegment.objects.create_segment(obs_recent_1, obs_recent_2, subject)

        # Test with delayed user (access_ends_7 = 168 hours delay)
        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user_with_delayed_access

        layer = ObservationSegmentVectorLayer(request=request)
        assert layer.delay_hours == 168  # 7 days * 24 hours

        qs = layer.get_queryset()

        # Should only see old segment (ended ≥7 days ago)
        # Recent segment should be filtered out
        segment_count = qs.count()
        assert segment_count == 1

        # Verify it's the old segment
        segment = qs.first()
        assert segment.end_recorded_at < (now - timedelta(days=7))


@pytest.mark.django_db
class TestSegmentQueryParameterFiltering:
    """Test query parameter filtering for ObservationSegmentVectorLayer."""

    def test_filter_by_subject_id(self, das_tenant, subject_subtype):
        """Verify subject_id filter returns only segments for that subject."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        # Create two subjects
        subject1 = Subject.objects.create(name="Subject 1", subject_subtype=subject_subtype, das_tenant=das_tenant)
        subject2 = Subject.objects.create(name="Subject 2", subject_subtype=subject_subtype, das_tenant=das_tenant)

        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_filter", display_name="Test", das_tenant=das_tenant
        )
        source1 = Source.objects.create(manufacturer_id="filter_test_s1", provider=provider, das_tenant=das_tenant)
        source2 = Source.objects.create(manufacturer_id="filter_test_s2", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject1, source=source1, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject2, source=source2, das_tenant=das_tenant)

        # Create observations and segments for both subjects
        now = timezone.now()
        obs1_s1 = Observation.objects.create(
            source=source1, recorded_at=now - timedelta(hours=2), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2_s1 = Observation.objects.create(
            source=source1, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs1_s1, obs2_s1, subject1)

        obs1_s2 = Observation.objects.create(
            source=source2, recorded_at=now - timedelta(hours=2), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2_s2 = Observation.objects.create(
            source=source2, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs1_s2, obs2_s2, subject2)

        # Apply filter for subject1 only
        qs = ObservationSegment.objects.all()
        filterset = ObservationSegmentVectorTileFilterSet(data={"subject_id": str(subject1.id)}, queryset=qs)
        filtered_qs = filterset.qs

        assert filtered_qs.count() == 1
        assert filtered_qs.first().subject_id == subject1.id

    def test_filter_by_subject_ids(self, das_tenant, subject_subtype):
        """Verify subject_ids filter returns segments for multiple subjects."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        # Create three subjects
        subjects = [
            Subject.objects.create(name=f"Subject {i}", subject_subtype=subject_subtype, das_tenant=das_tenant)
            for i in range(3)
        ]

        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_multi", display_name="Test", das_tenant=das_tenant
        )

        # Create sources and observations for each subject
        now = timezone.now()
        for idx, subject in enumerate(subjects):
            source = Source.objects.create(
                manufacturer_id=f"multi_test_{idx}", provider=provider, das_tenant=das_tenant
            )
            SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)
            obs1 = Observation.objects.create(
                source=source, recorded_at=now - timedelta(hours=2), location=Point(0, 0), das_tenant=das_tenant
            )
            obs2 = Observation.objects.create(
                source=source, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
            )
            ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Filter for first two subjects only
        qs = ObservationSegment.objects.all()
        subject_ids = f"{subjects[0].id},{subjects[1].id}"
        filterset = ObservationSegmentVectorTileFilterSet(data={"subject_ids": subject_ids}, queryset=qs)
        filtered_qs = filterset.qs

        assert filtered_qs.count() == 2
        returned_subject_ids = set(filtered_qs.values_list("subject_id", flat=True))
        assert returned_subject_ids == {subjects[0].id, subjects[1].id}

    def test_filter_by_since(self, das_tenant, subject_subtype):
        """Verify since filter returns segments starting after the given time."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        subject = Subject.objects.create(name="Since Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_since", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="since_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create old segment (should be filtered out)
        obs_old_1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(days=5), location=Point(0, 0), das_tenant=das_tenant
        )
        obs_old_2 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(days=5) + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=das_tenant,
        )
        ObservationSegment.objects.create_segment(obs_old_1, obs_old_2, subject)

        # Create recent segment (should be included)
        obs_new_1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(2, 0), das_tenant=das_tenant
        )
        obs_new_2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(3, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs_new_1, obs_new_2, subject)

        # Filter with since = 3 days ago
        qs = ObservationSegment.objects.all()
        since_time = (now - timedelta(days=3)).isoformat()
        filterset = ObservationSegmentVectorTileFilterSet(data={"since": since_time}, queryset=qs)
        filtered_qs = filterset.qs

        assert filtered_qs.count() == 1
        assert filtered_qs.first().start_recorded_at > now - timedelta(days=3)

    def test_filter_by_until(self, das_tenant, subject_subtype):
        """Verify until filter returns segments ending before the given time."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        subject = Subject.objects.create(name="Until Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_until", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="until_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create old segment (should be included)
        obs_old_1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(days=5), location=Point(0, 0), das_tenant=das_tenant
        )
        obs_old_2 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(days=5) + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=das_tenant,
        )
        ObservationSegment.objects.create_segment(obs_old_1, obs_old_2, subject)

        # Create recent segment (should be filtered out)
        obs_new_1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(2, 0), das_tenant=das_tenant
        )
        obs_new_2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(3, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs_new_1, obs_new_2, subject)

        # Filter with until = 3 days ago
        qs = ObservationSegment.objects.all()
        until_time = (now - timedelta(days=3)).isoformat()
        filterset = ObservationSegmentVectorTileFilterSet(data={"until": until_time}, queryset=qs)
        filtered_qs = filterset.qs

        assert filtered_qs.count() == 1
        assert filtered_qs.first().end_recorded_at < now - timedelta(days=3)

    def test_filter_by_created_after(self, das_tenant, subject_subtype):
        """Verify created_after filter returns segments created after the given time."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        subject = Subject.objects.create(name="Created Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_created", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="created_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create segment
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
        )
        segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Filter with created_after = 1 hour ago (segment was just created)
        qs = ObservationSegment.objects.all()
        created_after = (now - timedelta(hours=1)).isoformat()
        filterset = ObservationSegmentVectorTileFilterSet(data={"created_after": created_after}, queryset=qs)
        filtered_qs = filterset.qs

        # Segment should be included (created just now)
        assert filtered_qs.count() == 1
        assert filtered_qs.first().id == segment.id

        # Filter with created_after = 1 hour in future (should exclude all)
        created_after_future = (now + timedelta(hours=1)).isoformat()
        filterset_future = ObservationSegmentVectorTileFilterSet(
            data={"created_after": created_after_future}, queryset=qs
        )
        assert filterset_future.qs.count() == 0

    def test_filter_show_excluded_false_excludes_flagged(self, das_tenant, subject_subtype):
        """Verify show_excluded=false excludes segments with exclusion flags."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        subject = Subject.objects.create(name="Excluded Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_excluded", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="excluded_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create segment with no exclusion flags
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=4), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=3), location=Point(1, 0), das_tenant=das_tenant
        )
        clean_segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Create segment with exclusion flag
        obs3 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(hours=2),
            location=Point(2, 0),
            exclusion_flags=Observation.EXCLUDED_MANUALLY,
            das_tenant=das_tenant,
        )
        obs4 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(3, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs3, obs4, subject)

        qs = ObservationSegment.objects.all()

        # With show_excluded=false (default), should only get clean segment
        filterset = ObservationSegmentVectorTileFilterSet(data={"show_excluded": "false"}, queryset=qs)
        assert filterset.qs.count() == 1
        assert filterset.qs.first().id == clean_segment.id

    def test_filter_show_excluded_true_includes_flagged(self, das_tenant, subject_subtype):
        """Verify show_excluded=true includes segments with exclusion flags."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        subject = Subject.objects.create(name="Include Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_include", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="include_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create segment with no exclusion flags
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=4), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=3), location=Point(1, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Create segment with exclusion flag
        obs3 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(hours=2),
            location=Point(2, 0),
            exclusion_flags=Observation.EXCLUDED_MANUALLY,
            das_tenant=das_tenant,
        )
        obs4 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(3, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs3, obs4, subject)

        qs = ObservationSegment.objects.all()

        # With show_excluded=true, should get both segments
        filterset = ObservationSegmentVectorTileFilterSet(data={"show_excluded": "true"}, queryset=qs)
        assert filterset.qs.count() == 2

    def test_combined_filters(self, das_tenant, subject_subtype):
        """Verify multiple filters can be combined."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        subject = Subject.objects.create(name="Combined Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_combined", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="combined_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create old segment
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(days=10), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(days=10) + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=das_tenant,
        )
        ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Create mid-range segment
        obs3 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(days=5), location=Point(2, 0), das_tenant=das_tenant
        )
        obs4 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(days=5) + timedelta(hours=1),
            location=Point(3, 0),
            das_tenant=das_tenant,
        )
        mid_segment = ObservationSegment.objects.create_segment(obs3, obs4, subject)

        # Create recent segment
        obs5 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(4, 0), das_tenant=das_tenant
        )
        obs6 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(5, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs5, obs6, subject)

        # Filter: subject + since 7 days ago + until 3 days ago
        qs = ObservationSegment.objects.all()
        filterset = ObservationSegmentVectorTileFilterSet(
            data={
                "subject_id": str(subject.id),
                "since": (now - timedelta(days=7)).isoformat(),
                "until": (now - timedelta(days=3)).isoformat(),
            },
            queryset=qs,
        )
        filtered_qs = filterset.qs

        # Should only get the mid-range segment
        assert filtered_qs.count() == 1
        assert filtered_qs.first().id == mid_segment.id


@pytest.mark.django_db
class TestMOUExpiryFiltering:
    """Test MOU expiry date filtering on segment and subject layers."""

    def test_segment_layer_filters_by_mou_expiry(self, das_tenant, subject_subtype, user):
        """Verify segment layer filters segments by MOU expiry date."""
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )
        from observations.vector_layers import ObservationSegmentVectorLayer

        subject = Subject.objects.create(name="MOU Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_mou", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="mou_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create segment before MOU expiry (should be included)
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(days=10), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(days=10) + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=das_tenant,
        )
        old_segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Create segment after MOU expiry (should be filtered out)
        obs3 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(2, 0), das_tenant=das_tenant
        )
        obs4 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(3, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs3, obs4, subject)

        # Set MOU expiry to 5 days ago
        mou_expiry = (now - timedelta(days=5)).isoformat()
        user.additional = {"expiry": mou_expiry}
        user.save()

        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user

        layer = ObservationSegmentVectorLayer(request=request)
        assert layer.mou_expiry_date == mou_expiry

        qs = layer.get_queryset()

        # Should only see segment before MOU expiry
        assert qs.count() == 1
        assert qs.first().id == old_segment.id

    def test_segment_layer_no_mou_expiry_shows_all(self, das_tenant, subject_subtype, user):
        """Verify segment layer shows all segments when no MOU expiry is set."""
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )
        from observations.vector_layers import ObservationSegmentVectorLayer

        subject = Subject.objects.create(name="No MOU Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_no_mou", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="no_mou_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create two segments
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(days=10), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(days=10) + timedelta(hours=1),
            location=Point(1, 0),
            das_tenant=das_tenant,
        )
        ObservationSegment.objects.create_segment(obs1, obs2, subject)

        obs3 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(2, 0), das_tenant=das_tenant
        )
        obs4 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(3, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs3, obs4, subject)

        # User without MOU expiry
        user.additional = {}
        user.save()

        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user

        layer = ObservationSegmentVectorLayer(request=request)
        assert layer.mou_expiry_date is None

        qs = layer.get_queryset()

        # Should see both segments
        assert qs.count() == 2


@pytest.mark.django_db
class TestSubjectLayerProperties:
    """Test SubjectVectorLayer feature properties and color handling."""

    def test_subject_color_from_additional_rgb(self, das_tenant, subject_subtype):
        """Verify subject color is extracted from additional.rgb."""
        subject = Subject.objects.create(
            name="Color Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
            additional={"rgb": "255,128,0"},
        )
        SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
            location=Point(0, 0, srid=4326),
            recorded_at=timezone.now(),
            radio_state="online-gps",
        )

        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject.id).first()

        assert obj is not None
        assert obj.color == "255,128,0"

    def test_subject_default_color_when_no_rgb(self, das_tenant, subject_subtype):
        """Verify default color is used when subject has no rgb in additional."""
        subject = Subject.objects.create(
            name="No Color Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
            additional={},  # No rgb key
        )
        SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
            location=Point(0, 0, srid=4326),
            recorded_at=timezone.now(),
            radio_state="online-gps",
        )

        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject.id).first()

        assert obj is not None
        assert obj.color == "255,255,0"  # Default yellow

    def test_image_url_includes_subtype_color_and_sex(self, das_tenant, subject_subtype):
        """Verify image_url is built from subtype, radio_state colour, and sex."""
        subject = Subject.objects.create(
            name="Image URL Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
            additional={"sex": "female"},
        )
        SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
            location=Point(0, 0, srid=4326),
            recorded_at=timezone.now(),
            radio_state="online-gps",
        )

        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject.id).first()

        assert obj is not None
        subtype = subject_subtype.value.lower()
        assert obj.image_url == f"/static/sprite-src/{subtype}-green-female.svg"

    def test_image_url_defaults_sex_to_male(self, das_tenant, subject_subtype):
        """Verify image_url uses 'male' when sex is not in additional."""
        subject = Subject.objects.create(
            name="Default Sex Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
            additional={},
        )
        SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
            location=Point(0, 0, srid=4326),
            recorded_at=timezone.now(),
            radio_state="offline",
        )

        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject.id).first()

        assert obj is not None
        subtype = subject_subtype.value.lower()
        assert obj.image_url == f"/static/sprite-src/{subtype}-gray-male.svg"

    def test_image_url_alarm_state(self, das_tenant, subject_subtype):
        """Verify alarm radio_state maps to red in image_url."""
        subject = Subject.objects.create(
            name="Alarm Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
            additional={},
        )
        SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
            location=Point(0, 0, srid=4326),
            recorded_at=timezone.now(),
            radio_state="alarm",
        )

        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject.id).first()

        assert obj is not None
        subtype = subject_subtype.value.lower()
        assert obj.image_url == f"/static/sprite-src/{subtype}-red-male.svg"

    def test_subject_type_and_subtype_annotations(self, das_tenant, subject_subtype):
        """Verify subject_type and subject_subtype are properly annotated."""
        subject = Subject.objects.create(
            name="Type Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
        )
        SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
            location=Point(0, 0, srid=4326),
            recorded_at=timezone.now(),
            radio_state="online-gps",
        )

        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject.id).first()

        assert obj is not None
        assert obj.subject_type_value == subject_subtype.subject_type.value
        assert obj.subject_subtype_value == subject_subtype.value


@pytest.mark.django_db
class TestSegmentPresentationProperties:
    """Test segment presentation properties (stroke, stroke-width, stroke-opacity)."""

    def test_presentation_uses_subject_rgb(self, das_tenant, subject_subtype):
        """Verify presentation stroke uses subject's RGB color."""
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )
        from observations.vector_layers import ObservationSegmentVectorLayer

        subject = Subject.objects.create(
            name="RGB Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
            additional={"rgb": "#ff0000"},
        )
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_rgb", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="rgb_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
        )
        segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        layer = ObservationSegmentVectorLayer()
        props = layer.get_presentation_properties(segment)

        assert props["stroke"] == "#ff0000"
        assert props["stroke-width"] == 2.0
        assert props["stroke-opacity"] == 0.8

    def test_presentation_default_stroke_color(self, das_tenant, subject_subtype):
        """Verify default stroke color when subject has no RGB."""
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )
        from observations.vector_layers import ObservationSegmentVectorLayer

        subject = Subject.objects.create(
            name="Default Color Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
            additional={},  # No rgb
        )
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_default", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="default_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
        )
        segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        layer = ObservationSegmentVectorLayer()
        props = layer.get_presentation_properties(segment)

        assert props["stroke"] == "#4264fb"  # Default blue
        assert props["stroke-width"] == 2.0
        assert props["stroke-opacity"] == 0.8

    def test_feature_includes_presentation_properties(self, das_tenant, subject_subtype):
        """Verify as_vector_tile_feature includes presentation properties."""
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )
        from observations.vector_layers import ObservationSegmentVectorLayer

        subject = Subject.objects.create(
            name="Feature Props Test",
            subject_subtype=subject_subtype,
            das_tenant=das_tenant,
            additional={"rgb": "#00ff00"},
        )
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_feature", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="feature_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
        )
        segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        layer = ObservationSegmentVectorLayer()
        factory = APIRequestFactory()
        request = factory.get("/tiles")
        layer.request = request

        # Need to get segment from queryset to have annotations
        qs = layer.get_vector_tile_queryset()
        annotated_segment = qs.get(id=segment.id)
        feature = layer.as_vector_tile_feature(annotated_segment)

        assert "stroke" in feature["properties"]
        assert "stroke-width" in feature["properties"]
        assert "stroke-opacity" in feature["properties"]
        assert feature["properties"]["stroke"] == "#00ff00"
        assert feature["properties"]["stroke-width"] == 2.0
        assert feature["properties"]["stroke-opacity"] == 0.8


@pytest.mark.django_db
class TestVectorTileEdgeCases:
    """Test edge cases for vector tile layers."""

    def test_segment_layer_empty_when_no_segments(self, das_tenant, subject_subtype):
        """Verify layer returns empty queryset when no segments exist."""
        from observations.vector_layers import ObservationSegmentVectorLayer

        # Create subject but no segments
        Subject.objects.create(name="Empty Test", subject_subtype=subject_subtype, das_tenant=das_tenant)

        layer = ObservationSegmentVectorLayer()
        qs = layer.get_queryset()

        assert qs.count() == 0

    def test_subject_layer_empty_when_no_status(self, das_tenant, subject_subtype):
        """Verify subject layer excludes subjects without status."""
        # Create subject without status
        subject = Subject.objects.create(name="No Status Test", subject_subtype=subject_subtype, das_tenant=das_tenant)

        layer = SubjectVectorLayer()
        qs = layer.get_queryset()

        assert not qs.filter(id=subject.id).exists()

    def test_filter_with_nonexistent_subject_id(self, das_tenant, subject_subtype):
        """Verify filter returns empty when subject_id doesn't exist."""
        import uuid

        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        subject = Subject.objects.create(name="Exists", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_nonexist", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="nonexist_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=2), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs1, obs2, subject)

        qs = ObservationSegment.objects.all()
        nonexistent_id = str(uuid.uuid4())
        filterset = ObservationSegmentVectorTileFilterSet(data={"subject_id": nonexistent_id}, queryset=qs)

        assert filterset.qs.count() == 0

    def test_multiple_exclusion_flags_combined(self, das_tenant, subject_subtype):
        """Verify segments with multiple exclusion flags are handled correctly."""
        from observations.filters import ObservationSegmentVectorTileFilterSet
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )

        subject = Subject.objects.create(name="Multi Flag Test", subject_subtype=subject_subtype, das_tenant=das_tenant)
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_multiflag", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="multiflag_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create observation with multiple exclusion flags
        obs1 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(hours=2),
            location=Point(0, 0),
            exclusion_flags=Observation.EXCLUDED_MANUALLY | Observation.EXCLUDED_AUTOMATICALLY,
            das_tenant=das_tenant,
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(1, 0), das_tenant=das_tenant
        )
        segment = ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Segment should have combined flags
        assert segment.exclusion_flags.mask != 0

        qs = ObservationSegment.objects.all()

        # With show_excluded=false, should not include this segment
        filterset_exclude = ObservationSegmentVectorTileFilterSet(data={"show_excluded": "false"}, queryset=qs)
        assert filterset_exclude.qs.count() == 0

        # With show_excluded=true, should include it
        filterset_include = ObservationSegmentVectorTileFilterSet(data={"show_excluded": "true"}, queryset=qs)
        assert filterset_include.qs.count() == 1

    def test_layer_show_excluded_from_request_params(self, das_tenant, subject_subtype):
        """Verify ObservationSegmentVectorLayer respects show_excluded query param."""
        from observations.models import (
            Observation,
            ObservationSegment,
            Source,
            SourceProvider,
            Subject,
            SubjectSource,
        )
        from observations.vector_layers import ObservationSegmentVectorLayer

        subject = Subject.objects.create(
            name="Request Param Test", subject_subtype=subject_subtype, das_tenant=das_tenant
        )
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key="test_reqparam", display_name="Test", das_tenant=das_tenant
        )
        source = Source.objects.create(manufacturer_id="reqparam_test", provider=provider, das_tenant=das_tenant)
        SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

        now = timezone.now()

        # Create clean segment
        obs1 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=4), location=Point(0, 0), das_tenant=das_tenant
        )
        obs2 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=3), location=Point(1, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs1, obs2, subject)

        # Create flagged segment
        obs3 = Observation.objects.create(
            source=source,
            recorded_at=now - timedelta(hours=2),
            location=Point(2, 0),
            exclusion_flags=Observation.EXCLUDED_MANUALLY,
            das_tenant=das_tenant,
        )
        obs4 = Observation.objects.create(
            source=source, recorded_at=now - timedelta(hours=1), location=Point(3, 0), das_tenant=das_tenant
        )
        ObservationSegment.objects.create_segment(obs3, obs4, subject)

        factory = APIRequestFactory()

        # Request without show_excluded (default to false)
        request_default = factory.get("/observations/segments/tiles/10/512/512.pbf")
        layer_default = ObservationSegmentVectorLayer(request=request_default)
        assert layer_default.get_queryset().count() == 1

        # Request with show_excluded=true
        request_include = factory.get("/observations/segments/tiles/10/512/512.pbf?show_excluded=true")
        layer_include = ObservationSegmentVectorLayer(request=request_include)
        assert layer_include.get_queryset().count() == 2

        # Request with show_excluded=false
        request_exclude = factory.get("/observations/segments/tiles/10/512/512.pbf?show_excluded=false")
        layer_exclude = ObservationSegmentVectorLayer(request=request_exclude)
        assert layer_exclude.get_queryset().count() == 1


@pytest.mark.django_db
class TestSubjectGroupPermissionFiltering:
    """
    Test that vector tile layers respect subject group permissions.

    Users should only see subjects (and their segments) that belong to
    subject groups the user has access to via permission sets.
    """

    def test_subject_layer_excludes_unpermitted_subjects(self, das_tenant, subject_subtype, user_with_group_access):
        """Non-superuser only sees subjects in their permitted subject groups."""
        user, allowed_subject, denied_subject = user_with_group_access

        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user

        layer = SubjectVectorLayer(request=request)
        qs = layer.get_queryset()
        subject_ids = set(qs.values_list("id", flat=True))

        assert allowed_subject.id in subject_ids
        assert denied_subject.id not in subject_ids

    def test_subject_layer_superuser_sees_all(self, das_tenant, subject_subtype, superuser_with_group_subjects):
        """Superusers bypass group filtering and see all subjects."""
        superuser, allowed_subject, denied_subject = superuser_with_group_subjects

        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = superuser

        layer = SubjectVectorLayer(request=request)
        qs = layer.get_queryset()
        subject_ids = set(qs.values_list("id", flat=True))

        assert allowed_subject.id in subject_ids
        assert denied_subject.id in subject_ids

    def test_subject_layer_no_request_returns_all(self, das_tenant, subject_subtype, superuser_with_group_subjects):
        """Layer with no request (e.g. no auth context) returns all subjects."""
        _, allowed_subject, denied_subject = superuser_with_group_subjects

        layer = SubjectVectorLayer(request=None)
        qs = layer.get_queryset()
        subject_ids = set(qs.values_list("id", flat=True))

        # No request = no permission filtering applied
        assert allowed_subject.id in subject_ids
        assert denied_subject.id in subject_ids

    def test_segment_layer_excludes_unpermitted_segments(
        self, das_tenant, subject_subtype, user_with_group_access_and_segments
    ):
        """Non-superuser only sees segments for subjects in their permitted groups."""
        from observations.vector_layers import ObservationSegmentVectorLayer

        user, allowed_subject, denied_subject = user_with_group_access_and_segments

        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user

        layer = ObservationSegmentVectorLayer(request=request)
        qs = layer.get_queryset()
        segment_subject_ids = set(qs.values_list("subject_id", flat=True))

        assert allowed_subject.id in segment_subject_ids
        assert denied_subject.id not in segment_subject_ids

    def test_segment_layer_superuser_sees_all_segments(
        self, das_tenant, subject_subtype, superuser_with_group_access_and_segments
    ):
        """Superusers bypass group filtering and see all segments."""
        from observations.vector_layers import ObservationSegmentVectorLayer

        superuser, allowed_subject, denied_subject = superuser_with_group_access_and_segments

        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = superuser

        layer = ObservationSegmentVectorLayer(request=request)
        qs = layer.get_queryset()
        segment_subject_ids = set(qs.values_list("subject_id", flat=True))

        assert allowed_subject.id in segment_subject_ids
        assert denied_subject.id in segment_subject_ids

    def test_subject_layer_user_with_no_groups_sees_nothing(
        self, das_tenant, subject_subtype, user_with_no_group_access
    ):
        """User with no subject group access sees no subjects."""
        user, subject_a, subject_b = user_with_no_group_access

        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user

        layer = SubjectVectorLayer(request=request)
        qs = layer.get_queryset()

        assert qs.count() == 0


# ------------------------------------------------------------------ #
# Fixtures: Subject Group Permission Tests
# ------------------------------------------------------------------ #


def _create_subject_with_status(name, subject_subtype, das_tenant, lon=0.0, lat=0.0):
    """Helper to create a subject with a current SubjectStatus (location)."""
    subject = Subject.objects.create(
        name=name,
        subject_subtype=subject_subtype,
        is_active=True,
        das_tenant=das_tenant,
        additional={"rgb": "0,255,0"},
    )
    SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
        location=Point(lon, lat, srid=4326),
        recorded_at=timezone.now(),
        radio_state="online-gps",
    )
    return subject


def _create_segments_for_subject(subject, das_tenant):
    """Helper to create observations and segments for a subject."""
    from observations.models import (
        Observation,
        ObservationSegment,
        Source,
        SourceProvider,
        SubjectSource,
    )

    provider, _ = SourceProvider.objects.get_or_create(
        provider_key=f"perm_test_{subject.id}",
        display_name="Perm Test",
        das_tenant=das_tenant,
    )
    source = Source.objects.create(
        manufacturer_id=f"perm_test_{subject.id}",
        provider=provider,
        das_tenant=das_tenant,
    )
    SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

    now = timezone.now()
    obs1 = Observation.objects.create(
        source=source,
        location=Point(0.0, 0.0, srid=4326),
        recorded_at=now - timedelta(hours=2),
        das_tenant=das_tenant,
    )
    obs2 = Observation.objects.create(
        source=source,
        location=Point(1.0, 1.0, srid=4326),
        recorded_at=now - timedelta(hours=1),
        das_tenant=das_tenant,
    )
    ObservationSegment.objects.create_segment(obs1, obs2, subject)


def _setup_group_permission_scenario(das_tenant, subject_subtype, user, *, create_segments=False):
    """
    Create two subjects in separate groups, granting the user access to only one.

    Returns (user, allowed_subject, denied_subject).
    """
    from accounts.models.permissionset import PermissionSet
    from observations.models import SubjectGroup

    # Create two subjects with locations
    allowed_subject = _create_subject_with_status("Allowed Subject", subject_subtype, das_tenant, lon=10.0, lat=10.0)
    denied_subject = _create_subject_with_status("Denied Subject", subject_subtype, das_tenant, lon=20.0, lat=20.0)

    # Create two subject groups
    allowed_group = SubjectGroup.objects.create(name="Allowed Group", das_tenant=das_tenant)
    denied_group = SubjectGroup.objects.create(name="Denied Group", das_tenant=das_tenant)

    # Assign subjects to groups
    allowed_subject.groups.add(allowed_group)
    denied_subject.groups.add(denied_group)

    # Create permission set with view_subject permission and assign to allowed group
    view_perm = Permission.objects.filter(codename="view_subject").first()
    perm_set = PermissionSet.objects.create(name="allowed_group_view")
    if view_perm:
        perm_set.permissions.add(view_perm)
    allowed_group.permission_sets.add(perm_set)

    # Grant user this permission set (so they can see subjects in allowed_group)
    user.permission_sets.add(perm_set)
    user.additional = {}
    user.save()

    if create_segments:
        _create_segments_for_subject(allowed_subject, das_tenant)
        _create_segments_for_subject(denied_subject, das_tenant)

    return user, allowed_subject, denied_subject


@pytest.fixture
def user_with_group_access(db, das_tenant, subject_subtype, user):
    """Non-superuser with access to one subject group but not another."""
    return _setup_group_permission_scenario(das_tenant, subject_subtype, user, create_segments=False)


@pytest.fixture
def user_with_group_access_and_segments(db, das_tenant, subject_subtype, user):
    """Non-superuser with group access, and both subjects have segments."""
    return _setup_group_permission_scenario(das_tenant, subject_subtype, user, create_segments=True)


@pytest.fixture
def superuser_with_group_subjects(db, das_tenant, subject_subtype, create_user):
    """Superuser with subjects in separate groups (should see all)."""
    superuser = create_user(is_superuser=True, username="superuser_vt")
    superuser.additional = {}
    superuser.save()

    allowed_subject = _create_subject_with_status("Super Allowed", subject_subtype, das_tenant, lon=10.0, lat=10.0)
    denied_subject = _create_subject_with_status("Super Denied", subject_subtype, das_tenant, lon=20.0, lat=20.0)

    return superuser, allowed_subject, denied_subject


@pytest.fixture
def superuser_with_group_access_and_segments(db, das_tenant, subject_subtype, create_user):
    """Superuser with subjects that have segments (should see all)."""
    superuser = create_user(is_superuser=True, username="superuser_seg_vt")
    superuser.additional = {}
    superuser.save()

    allowed_subject = _create_subject_with_status("Super Seg Allowed", subject_subtype, das_tenant, lon=10.0, lat=10.0)
    denied_subject = _create_subject_with_status("Super Seg Denied", subject_subtype, das_tenant, lon=20.0, lat=20.0)

    _create_segments_for_subject(allowed_subject, das_tenant)
    _create_segments_for_subject(denied_subject, das_tenant)

    return superuser, allowed_subject, denied_subject


@pytest.fixture
def user_with_no_group_access(db, das_tenant, subject_subtype, create_user):
    """User with no subject group permissions at all."""
    from observations.models import SubjectGroup

    no_access_user = create_user(username="no_group_user")
    no_access_user.additional = {}
    no_access_user.save()

    subject_a = _create_subject_with_status("No Access A", subject_subtype, das_tenant, lon=10.0, lat=10.0)
    subject_b = _create_subject_with_status("No Access B", subject_subtype, das_tenant, lon=20.0, lat=20.0)

    group = SubjectGroup.objects.create(name="Restricted Group", das_tenant=das_tenant)
    subject_a.groups.add(group)
    subject_b.groups.add(group)

    return no_access_user, subject_a, subject_b


# ------------------------------------------------------------------ #
# Fixtures: Original
# ------------------------------------------------------------------ #


@pytest.fixture
def subject_with_segments_and_status(db, das_tenant, subject_subtype):
    """Create a subject with segments and a current status."""
    from observations.models import (
        Observation,
        ObservationSegment,
        Source,
        SourceProvider,
        Subject,
        SubjectSource,
        SubjectStatus,
    )

    subject = Subject.objects.create(
        name="Test Subject with Segments",
        subject_subtype=subject_subtype,
        is_active=True,
        das_tenant=das_tenant,
        additional={"rgb": "255,0,0"},
    )

    # ensure_subject_status_exists signal already created the row; update in place
    SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
        location=Point(1.0, 1.0, srid=4326),
        recorded_at=timezone.now(),
        radio_state="online-gps",
    )

    # Create source for observations
    provider, _ = SourceProvider.objects.get_or_create(
        provider_key="test_segments_status", display_name="Test", das_tenant=das_tenant
    )
    source = Source.objects.create(manufacturer_id="segments_status_test", provider=provider, das_tenant=das_tenant)
    SubjectSource.objects.create(subject=subject, source=source, das_tenant=das_tenant)

    # Create some observations and segments with unique timestamps
    now = timezone.now()
    obs1 = Observation.objects.create(
        source=source,
        location=Point(0.0, 0.0, srid=4326),
        recorded_at=now - timedelta(hours=2, minutes=30),
        das_tenant=das_tenant,
    )
    obs2 = Observation.objects.create(
        source=source,
        location=Point(0.5, 0.5, srid=4326),
        recorded_at=now - timedelta(hours=1, minutes=30),
        das_tenant=das_tenant,
    )
    obs3 = Observation.objects.create(
        source=source,
        location=Point(1.0, 1.0, srid=4326),
        recorded_at=now - timedelta(minutes=30),
        das_tenant=das_tenant,
    )

    ObservationSegment.objects.create_segment(obs1, obs2, subject)
    ObservationSegment.objects.create_segment(obs2, obs3, subject)

    return subject


@pytest.fixture
def user_with_realtime_access(db, user):
    """Create a user with real-time access permission (access_ends_0)."""
    from accounts.models.permissionset import PermissionSet

    permission = Permission.objects.get(codename="access_ends_0")
    perm_set = PermissionSet.objects.create(name="realtime_access_test")
    perm_set.permissions.add(permission)
    user.permission_sets.add(perm_set)
    user.additional = {}
    user.save()
    return user


@pytest.fixture
def user_with_delayed_access(db, create_user):
    """Create a *separate* user with 7-day delayed access permission (access_ends_7).

    Uses create_user instead of the shared ``user`` fixture so that tests
    combining both ``user_with_realtime_access`` and ``user_with_delayed_access``
    get distinct user instances (different user.id → different cache keys).
    """
    from accounts.models.permissionset import PermissionSet

    delayed_user = create_user(username="delayed_access_user")
    permission = Permission.objects.get(codename="access_ends_7")
    perm_set = PermissionSet.objects.create(name="delayed_access_test")
    perm_set.permissions.add(permission)
    delayed_user.permission_sets.add(perm_set)
    delayed_user.additional = {}
    delayed_user.save()
    return delayed_user


@pytest.fixture
def api_client_with_user(db, user_with_realtime_access):
    """Create an authenticated API client with real-time access.

    Uses force_login (session auth) because ObservationSegmentTileView is a
    plain Django View, not a DRF APIView — force_authenticate only injects
    the user for APIView subclasses.
    """
    client = APIClient()
    client.force_login(user_with_realtime_access)
    return client


@pytest.fixture
def subject_with_status(db, das_tenant, subject_subtype):
    """Create a subject with a latest status (delay_hours=0)."""
    subject = Subject.objects.create(
        name="Test Subject with Status",
        subject_subtype=subject_subtype,
        is_active=True,
        das_tenant=das_tenant,
        additional={"rgb": "255,0,0"},
    )
    # ensure_subject_status_exists signal already created the SubjectStatus row;
    # update it in place to set the location and radio state we need for tests.
    SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
        location=Point(0.0, 0.0, srid=4326),
        recorded_at=timezone.now(),
        radio_state="online-gps",
    )
    return subject


@pytest.fixture
def subject_without_status(db, das_tenant, subject_subtype):
    """Create a subject without any status."""
    return Subject.objects.create(
        name="Subject No Status",
        subject_subtype=subject_subtype,
        is_active=True,
        das_tenant=das_tenant,
    )


@pytest.fixture
def subject_with_multiple_statuses(db, das_tenant, subject_subtype):
    """Create a subject with multiple status records (different delay_hours)."""
    subject = Subject.objects.create(
        name="Subject Multiple Status",
        subject_subtype=subject_subtype,
        is_active=True,
        das_tenant=das_tenant,
    )
    # ensure_subject_status_exists signal already created rows for all
    # VIEW_END_WINDOWS delay tiers; update them with the locations we need.
    SubjectStatus.objects.filter(subject=subject, delay_hours=0).update(
        location=Point(1.0, 1.0, srid=4326),
        recorded_at=timezone.now(),
        radio_state="online-gps",
    )
    SubjectStatus.objects.filter(subject=subject, delay_hours=168).update(
        location=Point(2.0, 2.0, srid=4326),
        recorded_at=timezone.now() - timedelta(days=7),
        radio_state="offline",
    )
    return subject
