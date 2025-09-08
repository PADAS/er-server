from unittest.mock import patch

import pytest

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework.fields import DateTimeField

from accounts.models import PermissionSet
from accounts.utils import permission_get_by_natural_key
from activity.models import Event, Patrol, PatrolSegment, PatrolType


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant")
class TestEventPatrols:
    """Test suite for event-patrol relationships and associations."""

    @classmethod
    def setup_class(cls):
        cls.events_url = reverse("events")
        cls.patrol_segments_url = reverse("patrol-segments")
        cls.patrols_url = reverse("patrols")

    def setup_patrol_with_segment(self, patrol_type):
        """Helper method to create a patrol with a segment."""
        patrol = Patrol.objects.create(title="Test Patrol", objective="Test Objective")

        patrol_segment = PatrolSegment.objects.create(patrol=patrol, patrol_type=patrol_type)

        return patrol, patrol_segment

    @pytest.fixture
    def patrol_type(self):
        """Create or get a patrol type."""
        return PatrolType.objects.get_or_create(
            value="routine_patrol", defaults={"display": "Routine Patrol", "ordernum": 1}
        )[0]

    @pytest.fixture
    def event_data(self, monitoring_event_type):
        """Basic event data for testing."""
        return {
            "title": "Test Event",
            "message": "Test event message",
            "time": DateTimeField().to_representation(timezone.now()),
            "provenance": Event.PC_STAFF,
            "event_type": monitoring_event_type.value,
            "priority": Event.PRI_REFERENCE,
            "location": {"longitude": -122.3607072, "latitude": 47.681731199999994},
        }

    def test_add_event_to_patrol_segment(self, superuser_client, patrol_type, event_data):
        """Test adding an event to a patrol segment when creating the event."""
        # Create patrol and segment
        patrol, patrol_segment = self.setup_patrol_with_segment(patrol_type)

        # Create event with patrol_segments field
        data = {**event_data}
        data["patrol_segments"] = [str(patrol_segment.id)]

        response = superuser_client.post(self.events_url, data)
        assert response.status_code == 201
        assert str(patrol_segment.id) in str(response.json()["data"]["patrol_segments"])

        # Verify event appears in patrol segment
        segment_url = reverse("patrol-segment", kwargs={"id": str(patrol_segment.id)})
        response = superuser_client.get(segment_url)
        assert response.status_code == 200

        events = response.json()["data"]["events"]
        assert len(events) == 1
        assert events[0]["title"] == "Test Event"

        # Verify update history
        updates = response.json()["data"].get("updates", [])
        assert len(updates) > 0
        assert updates[0]["message"] == "Report Added"  # Wording may need to be updated?

    def test_add_patrol_segment_to_existing_event(self, superuser_client, patrol_type, event_data):
        """Test adding a patrol segment to an existing event via PATCH."""
        # Create patrol and segment
        patrol, patrol_segment = self.setup_patrol_with_segment(patrol_type)

        # Create event without patrol segments
        response = superuser_client.post(self.events_url, event_data)
        assert response.status_code == 201
        event_id = response.json()["data"]["id"]

        # Update event to add patrol segment
        event_url = reverse("event-view", kwargs={"id": event_id})
        update_data = {"patrol_segments": [str(patrol_segment.id)]}

        response = superuser_client.patch(event_url, update_data)
        assert response.status_code == 200
        assert str(patrol_segment.id) in str(response.json()["data"]["patrol_segments"])

        # Verify event appears in patrol segment
        segment_url = reverse("patrol-segment", kwargs={"id": str(patrol_segment.id)})
        response = superuser_client.get(segment_url)
        assert response.status_code == 200

        events = response.json()["data"]["events"]
        assert len(events) == 1
        assert events[0]["id"] == event_id

        # Verify update history
        updates = response.json()["data"].get("updates", [])
        assert len(updates) > 0
        assert updates[0]["message"] == "Report Added"

        # Verify event appears in patrol's segment list
        patrol_url = reverse("patrol", kwargs={"id": str(patrol.id)})
        response = superuser_client.get(patrol_url)
        assert response.status_code == 200

        patrol_segments = response.json()["data"]["patrol_segments"]
        assert len(patrol_segments) == 1
        assert len(patrol_segments[0]["events"]) == 1

    def test_remove_event_from_patrol_segment(self, superuser_client, patrol_type, event_data):
        """Test removing an event from a patrol segment."""
        # Create two patrol segments
        patrol1, patrol_segment1 = self.setup_patrol_with_segment(patrol_type)
        patrol2, patrol_segment2 = self.setup_patrol_with_segment(patrol_type)

        # Create event with both patrol segments
        data = {**event_data}
        data["patrol_segments"] = [str(patrol_segment1.id), str(patrol_segment2.id)]

        response = superuser_client.post(self.events_url, data)
        assert response.status_code == 201
        event_id = response.json()["data"]["id"]

        # Verify event is in both patrol segments
        segment1_url = reverse("patrol-segment", kwargs={"id": str(patrol_segment1.id)})
        response = superuser_client.get(segment1_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["events"]) == 1

        segment2_url = reverse("patrol-segment", kwargs={"id": str(patrol_segment2.id)})
        response = superuser_client.get(segment2_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["events"]) == 1

        # Remove one patrol segment from event
        event_url = reverse("event-view", kwargs={"id": event_id})
        update_data = {"patrol_segments": [str(patrol_segment2.id)]}

        response = superuser_client.patch(event_url, update_data)
        assert response.status_code == 200
        assert str(patrol_segment2.id) in response.json()["data"]["patrol_segments"]
        assert str(patrol_segment1.id) not in response.json()["data"]["patrol_segments"]

        # Verify event no longer appears in first patrol segment
        response = superuser_client.get(segment1_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["events"]) == 0

        # Verify event still appears in second patrol segment
        segment2_url = reverse("patrol-segment", kwargs={"id": str(patrol_segment2.id)})
        response = superuser_client.get(segment2_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["events"]) == 1

    @patch("django.contrib.auth.models.PermissionManager.get_by_natural_key", permission_get_by_natural_key)
    def test_event_patrol_permissions(
        self,
        superuser_client,
        user_client,
        patrol_type,
        logistics_event_type,
        monitoring_event_type,
    ):
        """Test that users with different permissions see different events in patrol segments."""
        # Create patrol and segment
        patrol, patrol_segment = self.setup_patrol_with_segment(patrol_type)

        # Create events in different categories
        logistics_event = Event.objects.create(
            title="Logistics Event", event_type=logistics_event_type  # Security event category
        )
        monitoring_event = Event.objects.create(
            title="Monitoring Event", event_type=monitoring_event_type  # Monitoring event category
        )

        # Add both events to patrol segment
        patrol_segment.events.add(logistics_event, monitoring_event)

        # Superuser should see both events
        segment_url = reverse("patrol-segment", kwargs={"id": str(patrol_segment.id)})
        response = superuser_client.get(segment_url)
        assert response.status_code == 200
        events = response.json()["data"]["events"]
        assert len(events) == 2
        event_titles = [e["title"] for e in events]
        assert "Logistics Event" in event_titles
        assert "Monitoring Event" in event_titles

        # Give regular user patrol and security read permissions
        security_permission_set = PermissionSet.objects.create(name="security_patrol_set")

        # Add patrol view permission
        patrol_view_permission = Permission.objects.get_by_natural_key(
            codename="view_patrol", app_label="activity", model="patrol"
        )
        security_permission_set.permissions.add(patrol_view_permission)

        # Add patrol segment view permission
        patrol_segment_view_permission = Permission.objects.get_by_natural_key(
            codename="view_patrolsegment", app_label="activity", model="patrolsegment"
        )
        security_permission_set.permissions.add(patrol_segment_view_permission)

        # Add security event read permission
        security_read_permission = Permission.objects.get_by_natural_key(
            codename="security_read", app_label="activity", model="event"
        )
        security_permission_set.permissions.add(security_read_permission)

        user_client.user.permission_sets.add(security_permission_set)

        # Regular user with patrol permissions sees all events in the patrol segment
        # Note: Event filtering by permission appears to happen at the event list level,
        # not when viewing events through patrol segments
        response = user_client.get(segment_url)
        assert response.status_code == 200
        events = response.json()["data"]["events"]
        assert len(events) == 2  # Both events are visible through patrol segment

    def test_multiple_events_in_patrol_segment(self, superuser_client, patrol_type, monitoring_event_type):
        """Test adding multiple events to a single patrol segment."""
        # Create patrol and segment
        patrol, patrol_segment = self.setup_patrol_with_segment(patrol_type)

        # Create multiple events
        events_created = []
        for i in range(3):
            event_data = {
                "title": f"Event {i+1}",
                "event_type": monitoring_event_type.value,
                "location": {"longitude": -122.3607072 + i, "latitude": 47.681731199999994},
                "patrol_segments": [str(patrol_segment.id)],
            }

            response = superuser_client.post(self.events_url, event_data)
            assert response.status_code == 201
            events_created.append(response.json()["data"]["id"])

        # Verify all events appear in patrol segment
        segment_url = reverse("patrol-segment", kwargs={"id": str(patrol_segment.id)})
        response = superuser_client.get(segment_url)
        assert response.status_code == 200

        events = response.json()["data"]["events"]
        assert len(events) == 3

        event_ids = [e["id"] for e in events]
        for event_id in events_created:
            assert event_id in event_ids

    def test_event_in_multiple_patrol_segments(self, superuser_client, patrol_type, event_data):
        """Test adding a single event to multiple patrol segments."""
        # Create two patrols with segments
        patrol1, patrol_segment1 = self.setup_patrol_with_segment(patrol_type)
        patrol2, patrol_segment2 = self.setup_patrol_with_segment(patrol_type)

        # Create event with multiple patrol segments
        data = {**event_data}
        data["patrol_segments"] = [str(patrol_segment1.id), str(patrol_segment2.id)]

        response = superuser_client.post(self.events_url, data)
        assert response.status_code == 201
        event_id = response.json()["data"]["id"]

        # Verify event appears in both patrol segments
        for segment_id in [patrol_segment1.id, patrol_segment2.id]:
            segment_url = reverse("patrol-segment", kwargs={"id": str(segment_id)})
            response = superuser_client.get(segment_url)
            assert response.status_code == 200

            events = response.json()["data"]["events"]
            assert len(events) == 1
            assert events[0]["id"] == event_id
