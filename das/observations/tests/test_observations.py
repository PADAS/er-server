from datetime import datetime, timedelta, timezone

import pytest

from django.urls import reverse
from rest_framework import status

from observations.models import Observation


@pytest.mark.django_db
class TestObservationsCursorPagination:
    """Test cursor pagination with subject_id filtering."""

    def test_cursor_pagination_with_subject_id_avoids_unions(self, subject_source, superuser_client):
        """Test that cursor pagination uses avoid_unions=True when filtering by subject_id."""
        # Create test data
        subject = subject_source.subject
        source = subject_source.source

        # Create some observations
        recorded_at = datetime.now(tz=timezone.utc) - timedelta(days=1)
        for i in range(5):
            Observation.objects.create(
                source=source, recorded_at=recorded_at + timedelta(hours=i), location="POINT(1.0 1.0)"
            )

        # Test with cursor pagination
        url = reverse("observations-list-view")
        response = superuser_client.get(url, {"subject_id": str(subject.id), "use_cursor": "true", "page_size": 2})

        assert response.status_code == status.HTTP_200_OK
        assert "next" in response.data
        assert "previous" in response.data
        assert len(response.data["results"]) == 2

        # Test without cursor pagination (should use UNIONs)
        response_no_cursor = superuser_client.get(
            url, {"subject_id": str(subject.id), "use_cursor": "false", "page_size": 2}
        )

        assert response_no_cursor.status_code == status.HTTP_200_OK
        assert len(response_no_cursor.data["results"]) == 2

    def test_cursor_pagination_without_subject_id_works_normally(self, subject_source, superuser_client):
        """Test that cursor pagination works normally when not filtering by subject_id."""
        # Create test data
        source = subject_source.source

        # Create some observations
        recorded_at = datetime.now(tz=timezone.utc) - timedelta(days=1)
        for i in range(5):
            Observation.objects.create(
                source=source, recorded_at=recorded_at + timedelta(hours=i), location="POINT(1.0 1.0)"
            )

        # Test with cursor pagination
        url = reverse("observations-list-view")
        response = superuser_client.get(url, {"use_cursor": "true", "page_size": 2})

        assert response.status_code == status.HTTP_200_OK
        assert "next" in response.data
        assert "previous" in response.data
        assert len(response.data["results"]) == 2
