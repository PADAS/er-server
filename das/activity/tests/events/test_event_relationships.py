import uuid
from unittest.mock import patch

import pytest

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import lorem_ipsum, timezone
from rest_framework.fields import DateTimeField

from accounts.models import PermissionSet
from accounts.utils import permission_get_by_natural_key
from activity.models import Event, EventRelationship


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant")
class TestEventRelationships:

    @classmethod
    def setup_class(cls):
        cls.events_url = reverse("events")

    def setup_relationships(self, collection_event_type, logistics_event_type, monitoring_event_type):
        event_collection = Event.objects.create(title="incident_collection_event", event_type=collection_event_type)
        event_a = Event.objects.create(title="Event_A", event_type=logistics_event_type)
        event_b = Event.objects.create(title="Event_B", event_type=monitoring_event_type)

        # Create relationships
        EventRelationship.objects.add_relationship(event_collection, event_a, "contains")
        EventRelationship.objects.add_relationship(event_collection, event_b, "contains")

        return event_collection, event_a, event_b

    @pytest.fixture
    def event_data(self):
        return {
            "title": "Test Event",
            "message": lorem_ipsum.paragraph(),
            "time": DateTimeField().to_representation(timezone.now()),
            "provenance": Event.PC_STAFF,
            "event_type": "",
            "priority": Event.PRI_REFERENCE,
            "location": {"longitude": 40.1353, "latitude": -1.891517},
        }

    def test_get_empty_relationships(self, superuser_client, collection_event_type, event_data):
        # create collection event
        data = {**event_data}
        data["event_type"] = collection_event_type.value

        response = superuser_client.post(self.events_url, data)
        assert response.status_code == 201
        collection_id = response.json()["data"]["id"]

        relationships_url = reverse("event-view-relationships", kwargs={"from_event_id": collection_id})
        response = superuser_client.get(relationships_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["results"]) == 0

    def test_get_relationships_from_non_existent_event(self, superuser_client):
        relationships_url = reverse("event-view-relationships", kwargs={"from_event_id": str(uuid.uuid4())})
        response = superuser_client.get(relationships_url)
        assert response.status_code == 404

    def test_create_relationship(self, superuser_client, base_event_types, event_data):
        collection_event_type, logistics_event_type, _ = base_event_types

        # create collection event
        data = {**event_data}
        data["event_type"] = collection_event_type.value

        response = superuser_client.post(self.events_url, data)
        assert response.status_code == 201
        collection_event_id = response.json()["data"]["id"]

        # create report event
        data = {**event_data}
        data["event_type"] = logistics_event_type.value

        response = superuser_client.post(self.events_url, data)
        assert response.status_code == 201
        logistics_event_id = response.json()["data"]["id"]

        # create relationship
        relationships_url = reverse("event-view-relationships", kwargs={"from_event_id": collection_event_id})
        data = {
            "to_event_id": logistics_event_id,
            "type": "contains",
        }
        response = superuser_client.post(relationships_url, data)
        assert response.status_code == 201

        # superuser should see all contained events
        response = superuser_client.get(relationships_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["results"]) == 1

    def test_get_relationships(self, superuser_client, base_event_types):
        event_collection = self.setup_relationships(*base_event_types)[0]

        relationships_url = reverse("event-view-relationships", kwargs={"from_event_id": str(event_collection.id)})
        response = superuser_client.get(relationships_url)
        assert response.status_code == 200

        relationships = response.json()["data"]["results"]
        assert len(relationships) == 2

        relationship_types = [relationship.get("type") for relationship in relationships]
        assert relationship_types == ["contains", "contains"]

    def test_delete_relationship(self, superuser_client, base_event_types):
        event_collection, event_a, _ = self.setup_relationships(*base_event_types)
        relationships_url = reverse("event-view-relationships", kwargs={"from_event_id": str(event_collection.id)})

        response = superuser_client.get(relationships_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["results"]) == 2

        relationship_url = reverse(
            "event-view-relationship",
            kwargs={
                "from_event_id": str(event_collection.id),
                "relationship_type": "contains",
                "to_event_id": str(event_a.id),
            },
        )
        response = superuser_client.delete(relationship_url)
        assert response.status_code == 200  # 204 No Content override

        response = superuser_client.get(relationships_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["results"]) == 1

    @patch("django.contrib.auth.models.PermissionManager.get_by_natural_key", permission_get_by_natural_key)
    def test_collection_event_contains_with_different_user_permissions(
        self, superuser_client, user_client, base_event_types
    ):
        """Test that users with different permissions see different contained events in a collection."""
        event_collection = self.setup_relationships(*base_event_types)[0]

        event_detail_url = reverse("event-view", kwargs={"id": str(event_collection.id)})
        response = superuser_client.get(event_detail_url)
        assert response.status_code == 200
        contained_events = response.json()["data"].get("contains", [])
        assert len(contained_events) == 2
        assert sorted([e.get("related_event", {}).get("title") for e in contained_events]) == ["Event_A", "Event_B"]

        guest_permission_set = PermissionSet.objects.create(name="guest_set")
        security_read_permission = Permission.objects.get_by_natural_key(
            codename="security_read", app_label="activity", model="event"
        )
        guest_permission_set.permissions.add(security_read_permission)
        user_client.user.permission_sets.add(guest_permission_set)

        # user should only see events they have permission for
        response = user_client.get(event_detail_url)
        assert response.status_code == 200

        contained_events = response.json()["data"].get("contains", [])
        assert len(contained_events) == 1
        assert contained_events[0].get("related_event", {}).get("title") == "Event_A"

    @patch("django.contrib.auth.models.PermissionManager.get_by_natural_key", permission_get_by_natural_key)
    def test_delete_relationship_permission_required(self, user_client, superuser_client, base_event_types):
        """Test that only users with delete_event_relationship permission can delete relationships."""
        event_collection, event_a, _ = self.setup_relationships(*base_event_types)
        relationship_url = reverse(
            "event-view-relationship",
            kwargs={
                "from_event_id": str(event_collection.id),
                "relationship_type": "contains",
                "to_event_id": str(event_a.id),
            },
        )

        # user without delete permission should get 403
        response = user_client.delete(relationship_url)
        assert response.status_code == 403
        assert "You don't have permission to delete event relationships" in str(response.json())

        # relationship should still exist
        relationships_url = reverse("event-view-relationships", kwargs={"from_event_id": str(event_collection.id)})
        response = superuser_client.get(relationships_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["results"]) == 2

        # give user the specific delete permission
        unlinker_permission_set = PermissionSet.objects.create(name="delete_relationship_permission_set")
        delete_permission = Permission.objects.get_by_natural_key(
            codename="delete_event_relationship", app_label="activity", model="eventrelationship"
        )
        unlinker_permission_set.permissions.add(delete_permission)
        user_client.user.permission_sets.add(unlinker_permission_set)

        # now the user should be able to delete
        response = user_client.delete(relationship_url)
        assert response.status_code == 200  # 204 No Content override

        response = superuser_client.get(relationships_url)
        assert response.status_code == 200
        assert len(response.json()["data"]["results"]) == 1
