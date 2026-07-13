import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from django.urls import reverse
from django.utils import lorem_ipsum
from django.utils import timezone as django_timezone
from rest_framework.fields import DateTimeField

from activity.models import Event
from activity.views.events.base import EventsCursorPagination
from factories import EventFactory, TenantFactory


@pytest.mark.usefixtures("tenant_settings", "das_tenant")
@pytest.mark.django_db
class TestEventViewListing:
    """Test event view listing methods."""

    base_url = reverse("events")

    def test_events_list(self, superuser_client, five_events) -> None:
        response = superuser_client.get(self.base_url)

        assert response.status_code == 200

    def test_events_list_with_multiple_event_ids(self, superuser_client, five_events) -> None:
        event_1 = five_events[0]
        event_2 = five_events[2]

        url = f"{self.base_url}?event_ids={event_1.pk}&event_ids={event_2.pk}"

        response = superuser_client.get(url)
        results = response.data["results"]

        assert response.status_code == 200
        assert len(results) == 2

        ids_expected = [str(event_1.pk), str(event_2.pk)]

        assert all(event_obj.get("id") in ids_expected for event_obj in results)


def _set_created_at(event: Event, created_at: datetime) -> None:
    """created_at is auto_now_add, so override it directly in the DB to make ordering deterministic."""
    Event.objects.filter(pk=event.pk).update(created_at=created_at)


@pytest.mark.usefixtures("tenant_settings", "das_tenant")
@pytest.mark.django_db
class TestEventsCursorPagination:
    """Test the opt-in cursor pagination mode on the events list API."""

    base_url = reverse("events")

    def _create_ordered_events(self, count: int) -> list[Event]:
        """Create `count` events with strictly increasing created_at; returns them oldest-first."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        events = EventFactory.create_batch(count)
        for index, event in enumerate(events):
            _set_created_at(event, base + timedelta(minutes=index))
        return events

    def test_cursor_response_has_next_previous_and_respects_page_size(self, superuser_client) -> None:
        self._create_ordered_events(5)

        response = superuser_client.get(self.base_url, {"use_cursor": "true", "page_size": 2})

        assert response.status_code == 200
        assert "next" in response.data
        assert "previous" in response.data
        assert len(response.data["results"]) == 2

    def test_default_response_uses_page_number_shape(self, superuser_client) -> None:
        self._create_ordered_events(5)

        response = superuser_client.get(self.base_url, {"page_size": 2})

        assert response.status_code == 200
        assert "count" in response.data
        assert "results" in response.data
        assert response.data["count"] == 5

    def test_use_cursor_false_uses_page_number_shape(self, superuser_client) -> None:
        self._create_ordered_events(5)

        response = superuser_client.get(self.base_url, {"use_cursor": "false", "page_size": 2})

        assert response.status_code == 200
        assert "count" in response.data
        assert response.data["count"] == 5

    def test_cursor_ordering_is_newest_first(self, superuser_client) -> None:
        events = self._create_ordered_events(3)  # oldest-first

        response = superuser_client.get(self.base_url, {"use_cursor": "true", "page_size": 3})

        result_ids = [row["id"] for row in response.data["results"]]
        expected_newest_first = [str(event.pk) for event in reversed(events)]

        assert result_ids == expected_newest_first

    def test_cursor_is_stable_when_event_inserted_between_pages(self, superuser_client) -> None:
        events = self._create_ordered_events(4)  # oldest-first, created_at minutes 0..3

        first_page = superuser_client.get(self.base_url, {"use_cursor": "true", "page_size": 2})
        first_ids = [row["id"] for row in first_page.data["results"]]
        # newest two events first
        assert first_ids == [str(events[3].pk), str(events[2].pk)]

        # Insert a brand-new event (now-ish) that sorts ahead of everything fetched so far.
        new_event = EventFactory.create()
        _set_created_at(new_event, datetime(2026, 1, 2, tzinfo=timezone.utc))

        next_url = first_page.data["next"]
        assert next_url is not None
        second_page = superuser_client.get(next_url)
        second_ids = [row["id"] for row in second_page.data["results"]]

        # The cursor anchors on the first page's boundary, so the originally-paged
        # items neither shift nor duplicate; the newly inserted event does not appear.
        assert second_ids == [str(events[1].pk), str(events[0].pk)]
        assert str(new_event.pk) not in first_ids
        assert str(new_event.pk) not in second_ids

    def test_default_response_carries_deprecation_headers(self, superuser_client) -> None:
        self._create_ordered_events(2)

        response = superuser_client.get(self.base_url, {"page_size": 2})

        assert response.has_header("Deprecation")
        assert response.has_header("Sunset")

    def test_cursor_response_omits_deprecation_headers(self, superuser_client) -> None:
        self._create_ordered_events(2)

        response = superuser_client.get(self.base_url, {"use_cursor": "true", "page_size": 2})

        assert not response.has_header("Deprecation")
        assert not response.has_header("Sunset")

    def test_post_does_not_carry_deprecation_headers(self, superuser_client, collection_event_type) -> None:
        # Event creation (POST) is not deprecated; only page-based GET pagination is.
        data = {
            "title": "Test Event",
            "message": lorem_ipsum.paragraph(),
            "time": DateTimeField().to_representation(django_timezone.now()),
            "provenance": Event.PC_STAFF,
            "event_type": collection_event_type.value,
            "priority": Event.PRI_REFERENCE,
            "location": {"longitude": 40.1353, "latitude": -1.891517},
        }

        response = superuser_client.post(self.base_url, data)

        assert response.status_code == 201
        assert not response.has_header("Deprecation")
        assert not response.has_header("Sunset")

    def test_cursor_results_are_tenant_scoped(self, superuser_client) -> None:
        own_events = self._create_ordered_events(2)

        # An event belonging to a different tenant must not leak into cursor results.
        other_tenant = TenantFactory.create(id=uuid.uuid4(), domain="other-tenant.example.com")
        foreign_event = EventFactory.create(das_tenant=other_tenant)

        response = superuser_client.get(self.base_url, {"use_cursor": "true", "page_size": 50})

        result_ids = {row["id"] for row in response.data["results"]}

        assert result_ids == {str(event.pk) for event in own_events}
        assert str(foreign_event.pk) not in result_ids

    def test_cursor_page_size_clamped_to_max_page_size(self, superuser_client) -> None:
        # Temporarily lower max_page_size so the clamp can be exercised with a handful of
        # events instead of creating MAX_PAGE_SIZE + 1 rows.
        lowered_max_page_size = 3
        self._create_ordered_events(lowered_max_page_size + 2)

        with patch.object(EventsCursorPagination, "max_page_size", lowered_max_page_size):
            response = superuser_client.get(
                self.base_url,
                {"use_cursor": "true", "page_size": lowered_max_page_size + 9999},
            )

        assert response.status_code == 200
        assert len(response.data["results"]) == lowered_max_page_size

    def test_cursor_sort_by_mismatched_ordering_is_rejected(self, superuser_client) -> None:
        self._create_ordered_events(2)

        response = superuser_client.get(
            self.base_url,
            {"use_cursor": "true", "sort_by": "event_time"},
        )

        assert response.status_code == 400

    def test_cursor_sort_by_matching_enforced_ordering_is_allowed(self, superuser_client) -> None:
        events = self._create_ordered_events(2)  # oldest-first

        response = superuser_client.get(
            self.base_url,
            {"use_cursor": "true", "sort_by": "-created_at"},
        )

        assert response.status_code == 200
        result_ids = [row["id"] for row in response.data["results"]]
        assert result_ids == [str(event.pk) for event in reversed(events)]
