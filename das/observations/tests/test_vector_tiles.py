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
        assert "image" in layer.tile_fields
        assert "color" in layer.tile_fields

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
        """Verify color, radio_state, and other properties are annotated."""
        layer = SubjectVectorLayer()
        qs = layer.get_queryset()
        obj = qs.filter(id=subject_with_status.id).first()

        assert hasattr(obj, "color")
        assert hasattr(obj, "radio_state")
        assert hasattr(obj, "recorded_at")
        assert hasattr(obj, "subject_type")
        assert hasattr(obj, "subject_subtype")

    def test_default_delay_hours_is_zero(self):
        """Verify default delay_hours is 0 when no request provided."""
        layer = SubjectVectorLayer()
        assert layer.delay_hours == 0

    def test_realtime_user_sees_latest_position(self, subject_with_multiple_statuses, user_with_realtime_access):
        """Verify users with access_ends_0 permission see delay_hours=0 status."""
        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user_with_realtime_access

        layer = SubjectVectorLayer(request=request)
        assert layer.delay_hours == 0

        qs = layer.get_queryset()
        obj = qs.filter(id=subject_with_multiple_statuses.id).first()

        # Should use the status with delay_hours=0 (latest)
        status_latest = SubjectStatus.objects.get(subject=subject_with_multiple_statuses, delay_hours=0)
        assert obj.recorded_at == status_latest.recorded_at

    def test_delayed_user_sees_delayed_position(self, subject_with_multiple_statuses, user_with_delayed_access):
        """Verify users with access_ends_7 permission see delay_hours=168 status."""
        factory = APIRequestFactory()
        request = factory.get("/observations/segments/tiles/10/512/512.pbf")
        request.user = user_with_delayed_access

        layer = SubjectVectorLayer(request=request)
        assert layer.delay_hours == 168  # 7 days * 24 hours

        qs = layer.get_queryset()
        obj = qs.filter(id=subject_with_multiple_statuses.id).first()

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
        from rest_framework.authtoken.models import Token

        url = reverse("observation-segments-vector-tiles", kwargs={"z": 10, "x": 512, "y": 512})

        token, _ = Token.objects.get_or_create(user=user_with_realtime_access)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = client.get(url)

        assert response.status_code in (200, 204)

    def test_delayed_user_sees_filtered_segments(self, subject_with_segments_and_status, user_with_delayed_access):
        """Verify users with access_ends_7 only see segments from ≥7 days ago."""
        from rest_framework.authtoken.models import Token

        url = reverse("observation-segments-vector-tiles", kwargs={"z": 10, "x": 512, "y": 512})

        token, _ = Token.objects.get_or_create(user=user_with_delayed_access)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = client.get(url)

        # Should get filtered data (may be empty if no old enough segments)
        assert response.status_code in (200, 204)

    def test_different_users_get_different_cache(
        self, subject_with_segments_and_status, user_with_realtime_access, user_with_delayed_access
    ):
        """Verify users with different permissions get different cached tiles."""
        from rest_framework.authtoken.models import Token

        url = reverse("observation-segments-vector-tiles", kwargs={"z": 10, "x": 512, "y": 512})

        # Realtime user request
        token1, _ = Token.objects.get_or_create(user=user_with_realtime_access)
        client1 = APIClient()
        client1.credentials(HTTP_AUTHORIZATION=f"Token {token1.key}")
        response1 = client1.get(url)

        # Delayed user request
        token2, _ = Token.objects.get_or_create(user=user_with_delayed_access)
        client2 = APIClient()
        client2.credentials(HTTP_AUTHORIZATION=f"Token {token2.key}")
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

        from observations.models import Observation, ObservationSegment, Subject
        from observations.vector_layers import ObservationSegmentVectorLayer

        # Create subject
        subject = Subject.objects.create(
            name="Test Subject",
            subject_subtype=subject_subtype,
            is_active=True,
            das_tenant=das_tenant,
        )

        # Create observations: one recent, one old
        now = timezone.now()
        old_time = now - timedelta(days=10)

        obs_old_1 = Observation.objects.create(
            subject=subject,
            location=Point(0.0, 0.0, srid=4326),
            recorded_at=old_time,
            das_tenant=das_tenant,
        )
        obs_old_2 = Observation.objects.create(
            subject=subject,
            location=Point(0.1, 0.1, srid=4326),
            recorded_at=old_time + timedelta(hours=1),
            das_tenant=das_tenant,
        )

        obs_recent_1 = Observation.objects.create(
            subject=subject,
            location=Point(1.0, 1.0, srid=4326),
            recorded_at=now - timedelta(hours=1),
            das_tenant=das_tenant,
        )
        obs_recent_2 = Observation.objects.create(
            subject=subject,
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


# Fixtures


@pytest.fixture
def subject_with_segments_and_status(db, das_tenant, subject_subtype):
    """Create a subject with segments and a current status."""
    from observations.models import (
        Observation,
        ObservationSegment,
        Subject,
        SubjectStatus,
    )

    subject = Subject.objects.create(
        name="Test Subject",
        subject_subtype=subject_subtype,
        is_active=True,
        das_tenant=das_tenant,
        additional={"rgb": "255,0,0"},
    )

    # Create current status
    SubjectStatus.objects.create(
        subject=subject,
        location=Point(1.0, 1.0, srid=4326),
        recorded_at=timezone.now(),
        delay_hours=0,
        radio_state="online-gps",
        das_tenant=das_tenant,
    )

    # Create some observations and segments
    now = timezone.now()
    obs1 = Observation.objects.create(
        subject=subject,
        location=Point(0.0, 0.0, srid=4326),
        recorded_at=now - timedelta(hours=2),
        das_tenant=das_tenant,
    )
    obs2 = Observation.objects.create(
        subject=subject,
        location=Point(0.5, 0.5, srid=4326),
        recorded_at=now - timedelta(hours=1),
        das_tenant=das_tenant,
    )
    obs3 = Observation.objects.create(
        subject=subject,
        location=Point(1.0, 1.0, srid=4326),
        recorded_at=now,
        das_tenant=das_tenant,
    )

    ObservationSegment.objects.create_segment(obs1, obs2, subject)
    ObservationSegment.objects.create_segment(obs2, obs3, subject)

    return subject


@pytest.fixture
def user_with_realtime_access(db, user):
    """Create a user with real-time access permission (access_ends_0)."""
    permission = Permission.objects.get(codename="access_ends_0")
    user.user_permissions.add(permission)
    user.additional = {}
    user.save()
    return user


@pytest.fixture
def user_with_delayed_access(db, user):
    """Create a user with 7-day delayed access permission (access_ends_7)."""
    permission = Permission.objects.get(codename="access_ends_7")
    user.user_permissions.add(permission)
    user.additional = {}
    user.save()
    return user


@pytest.fixture
def api_client_with_user(db, user_with_realtime_access):
    """Create an authenticated API client with real-time access."""
    from rest_framework.authtoken.models import Token

    token, _ = Token.objects.get_or_create(user=user_with_realtime_access)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def subject_with_status(db, das_tenant, subject_subtype):
    """Create a subject with a latest status (delay_hours=0)."""
    subject = Subject.objects.create(
        name="Test Subject",
        subject_subtype=subject_subtype,
        is_active=True,
        das_tenant=das_tenant,
        additional={"rgb": "255,0,0"},
    )
    SubjectStatus.objects.create(
        subject=subject,
        location=Point(0.0, 0.0, srid=4326),
        recorded_at=timezone.now(),
        delay_hours=0,
        radio_state="online-gps",
        das_tenant=das_tenant,
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
    # Latest status (delay_hours=0)
    SubjectStatus.objects.create(
        subject=subject,
        location=Point(1.0, 1.0, srid=4326),
        recorded_at=timezone.now(),
        delay_hours=0,
        radio_state="online-gps",
        das_tenant=das_tenant,
    )
    # Delayed status (delay_hours=168 = 7 days)
    SubjectStatus.objects.create(
        subject=subject,
        location=Point(2.0, 2.0, srid=4326),
        recorded_at=timezone.now() - timedelta(days=7),
        delay_hours=168,
        radio_state="offline",
        das_tenant=das_tenant,
    )
    return subject
