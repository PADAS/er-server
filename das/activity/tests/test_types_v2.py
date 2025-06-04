import json
from pathlib import Path

import pytest

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from activity.constants import PRI_IMPORTANT, PRI_URGENT
from activity.models import AlertRule, Event, EventType
from activity.serializers.events_v2 import EventTypeSerializer


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypesV2:
    """
    Tests for the EventTypesViewSet - V2 Event Types API.

    Some of these tests are relying on the `inital_data.json` fixture.

    """

    expected_fields = [
        "id",
        "value",
        "display",
        "category",
        "is_active",
        "is_collection",
        "has_events_assigned",
        "ordernum",
        "default_priority",
        "default_state",
        "geometry_type",
        "resolve_time",
        "auto_resolve",
        "icon_id",
        "url",
    ]

    def test_get_event_types_list(self, superuser_client, cat1_cat2_event_types):

        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0
        for field in self.expected_fields:
            assert field in response.data[0]

    def test_event_types_list_does_not_include_v1_ones(self, superuser_client, cat1_cat2_event_types, five_event_types):
        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        response_ids = {et_data["id"] for et_data in response.data}
        v1_count = v2_count = 0

        for et in EventType.objects.filter(category__is_active=True, is_active=True):
            if et.version == EventType.VersionChoices.VERSION_2:
                assert str(et.id) in response_ids
                v2_count += 1
            else:
                assert str(et.id) not in response_ids
                v1_count += 1
        assert v1_count > 0
        assert v2_count == 4  # 4 active v2 event types in the cat1_cat2_event_types fixture

    def test_event_types_list_does_not_include_inactive_ones(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # assert ids of event types are in the response if they are active
        response_ids = {et["id"] for et in response.data}
        for et in cat1_cat2_event_types:
            if et.is_active:
                assert str(et.id) in response_ids
            else:
                assert str(et.id) not in response_ids

    def test_event_types_list_include_inactive_param(self, superuser_client, cat1_cat2_event_types):
        """
        If ?include_inactive=true is passed, inactive event types should be included.
        """

        url = reverse("v2-eventtype-list")
        # By default, no inactive
        response = superuser_client.get(url)
        active_ids = {et["id"] for et in response.data}
        for et in cat1_cat2_event_types:
            if et.is_active:
                assert str(et.id) in active_ids
            else:
                assert str(et.id) not in active_ids

        # Now include_inactive=true
        response = superuser_client.get(url, {"include_inactive": "true"})
        all_ids = {et["id"] for et in response.data}
        for et in cat1_cat2_event_types:
            assert str(et.id) in all_ids

    def test_filter_event_types_by_category(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        # Filter by category "cat1"
        response = superuser_client.get(url, {"category": "cat1"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 3
        for et in response.data:
            assert et["category"] == "cat1"
        # Filter by category "cat2"
        response = superuser_client.get(url, {"category": "cat2"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        for et in response.data:
            assert et["category"] == "cat2"

    def test_filter_event_types_by_multiple_categories(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url, {"category": "cat1,cat2"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 4
        for et in response.data:
            assert et["category"] in ["cat1", "cat2"]

    def test_filter_event_types_by_invalid_category(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url, {"category": "invalid_category"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "category" in response.data
        assert "is not one of the available choices." in response.content.decode("utf-8")

    def test_filter_event_types_by_is_collection(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        # Filter where is_collection is true
        response = superuser_client.get(url, {"is_collection": "true"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        for et in response.data:
            assert et["is_collection"] is True
        # Filter where is_collection is false
        response = superuser_client.get(url, {"is_collection": "false"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 3
        for et in response.data:
            assert et["is_collection"] is False

    def test_filter_event_types_by_updated_since(self, superuser_client, cat1_cat2_event_types):
        # Let's set one record to be older than a cutoff time.
        et = cat1_cat2_event_types[0]
        # Bypass auto_now behavior by using .update() to set a past update time
        past_time = timezone.now() - timezone.timedelta(days=1)
        EventType.objects.filter(id=et.id).update(updated_at=past_time)
        et.refresh_from_db()
        assert et.updated_at == past_time

        # Cutoff time 12 hours ago
        cutoff = timezone.now() - timezone.timedelta(hours=12)

        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url, {"updated_since": cutoff.isoformat()})
        assert response.status_code == status.HTTP_200_OK

        returned_ids = {et_data["id"] for et_data in response.data}
        # The one updated in the past should not appear
        assert str(et.id) not in returned_ids
        for other in cat1_cat2_event_types[1:]:
            if not other.is_active:
                continue
            assert str(other.id) in returned_ids

    def test_get_event_type_detail(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(target.id)
        assert response.data["value"] == target.value
        assert response.has_header("ETag")

        for field in self.expected_fields:
            assert field in response.data

    def test_get_event_type_detail_by_uuid(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": str(target.id)})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(target.id)
        assert response.data["value"] == target.value
        assert response.has_header("ETag")

        for field in self.expected_fields:
            assert field in response.data

    def test_event_type_detail_not_found(self, superuser_client):
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": "nonexistent"})
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_v1_event_type_detail_returns_not_found(self, superuser_client, five_event_types):
        v1_et = five_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": v1_et.value})
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_event_type_detail_inactive(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[1]
        target.set_to_inactive()
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_event_type_detail_inactive_include_inactive_param(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[1]
        target.set_to_inactive()
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        response = superuser_client.get(url, {"include_inactive": "true"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(target.id)

    def test_event_type_detail_field_has_events_assigned(self, superuser_client, cat1_cat2_event_types, caplog):
        """
        Test that the "has_events_assigned" field in the event type detail is correct.
        """

        et_with_events = cat1_cat2_event_types[0]
        et_no_events = cat1_cat2_event_types[1]
        warning_msg = "Missing `in_use` annotation in EventType"

        # Create an event referencing the first event type.
        Event.objects.create(event_type=et_with_events)

        caplog.clear()
        caplog.set_level("WARNING")

        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": et_with_events.value})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["has_events_assigned"] is True
        assert warning_msg not in caplog.text

        # Test endpoint response for an event type without associated events.
        caplog.clear()
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": et_no_events.value})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["has_events_assigned"] is False
        assert warning_msg not in caplog.text

        # Now, test that the warning is in place when the `in_use` annotation is missing
        caplog.clear()
        et_serializer = EventTypeSerializer()
        assert et_serializer.get_has_events_assigned(et_with_events) is True
        assert warning_msg in caplog.text

    @pytest.mark.parametrize(
        "json_schema_fixture",
        [
            "valid_nested_collection_schema.json",
            "valid_user_choices_schema.json",
        ],
    )
    def test_post_event_type_with_valid_schema(self, superuser_client, cat1_cat2_categories, json_schema_fixture):
        cat1, _ = cat1_cat2_categories
        fixture_path = Path(__file__).parent / "fixtures" / json_schema_fixture
        with open(fixture_path, encoding="utf-8") as f:
            schema = json.load(f)

        data = {
            "display": "Simple Report",
            "value": "simple_report",
            "category": cat1.value,
            "schema": schema,
            "readonly": True,
        }
        url = reverse("v2-eventtype-list")
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_201_CREATED
        assert "resource_url" in response.data
        assert response.data["resource_url"] == reverse(
            "v2-eventtype-detail", kwargs={"eventtype_value": data["value"]}
        )

        new_eventtype = EventType.objects.get(value=data["value"])
        assert new_eventtype.readonly is True
        assert new_eventtype.version == EventType.VersionChoices.VERSION_2
        assert new_eventtype.category == cat1

    def test_post_event_type_with_invalid_schema(self, superuser_client, cat1_cat2_categories):
        cat1, _ = cat1_cat2_categories
        data = {
            "display": "Simple Report",
            "value": "simple_report",
            "category": cat1.value,
            "schema": {"json": {"$schema": "https://json-schema.org/draft/2020-12/schema"}, "ui": {"key": "value"}},
        }
        url = reverse("v2-eventtype-list")
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "schema" in response.data
        assert "Invalid JSON Schema:" in response.data["schema"][0]

    def test_post_event_type_with_wrong_schema_draft(self, superuser_client, cat1_cat2_categories):
        cat1, _ = cat1_cat2_categories
        data = {
            "display": "Simple Report",
            "value": "simple_report",
            "category": cat1.value,
            "schema": {
                "json": {
                    "$schema": "https://json-schema.org/draft/-12/schema",
                    "type": "object",
                    "properties": {
                        "json": {
                            "type": "object",
                            "properties": {"$schema": {"type": "string"}},
                            "required": ["$schema"],
                        },
                        "ui": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
                    },
                    "required": ["json", "ui"],
                },
                "ui": {"key": "value"},
            },
        }
        url = reverse("v2-eventtype-list")
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {
            "schema": ["$schema must be https://json-schema.org/draft/2020-12/schema"],
            "status": {"code": 400, "message": "Bad Request"},
        }

    def test_list_event_types_conditional_schema(self, superuser_client, five_event_types):
        """Verify `schema` is included only when `include_schema=true` query param is present."""
        url = reverse("v2-eventtype-list")

        # Test without include_schema
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        for item in response.data:
            assert "schema" not in item

        # Test with include_schema=true
        response = superuser_client.get(url, {"include_schema": "true"})
        assert response.status_code == status.HTTP_200_OK
        for item in response.data:
            assert "schema" in item  # Schema should now be present

    def test_retrieve_event_type_conditional_schema(self, superuser_client, cat1_cat2_event_types):
        """Verify `schema` is included on detail view only when `include_schema=true` query param is present."""
        event_type = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": event_type.value})

        # Test without include_schema
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "schema" not in response.data

        # Test with include_schema=true
        response = superuser_client.get(url, {"include_schema": "true"})
        assert response.status_code == status.HTTP_200_OK
        assert "schema" in response.data  # Schema should now be present

    def test_put_event_type_success(self, superuser_client, cat1_fire_v2_event_type, cat1_cat2_categories):
        target_et = cat1_fire_v2_event_type  # fixture with known valid schema
        original_updated_at = target_et.updated_at

        # Fetch current data via GET to ensure proper serialization and context for PUT payload
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target_et.value})
        response_get = superuser_client.get(url, {"include_schema": "true"})
        assert response_get.status_code == status.HTTP_200_OK
        put_payload = response_get.data.copy()

        # Remove read-only fields and fields not meant to be part of the core update payload
        excluded_fields = ["id", "url", "has_events_assigned", "icon_id"]
        for fld in excluded_fields:
            del put_payload[fld]

        # Make some changes
        new_display = "Updated Display Name via PUT"
        new_priority = PRI_IMPORTANT
        new_icon_slug = "fire-amber.svg"  # Use a known valid icon slug
        new_category_value = cat1_cat2_categories[1].value  # cat2 value

        put_payload["display"] = new_display
        put_payload["default_priority"] = new_priority
        put_payload["is_active"] = False
        put_payload["icon"] = new_icon_slug
        put_payload["category"] = new_category_value

        response = superuser_client.put(url, data=put_payload)

        assert response.status_code == status.HTTP_200_OK, response.content

        # Check updated fields
        target_et.refresh_from_db()

        assert target_et.display == new_display
        assert target_et.default_priority == new_priority
        assert target_et.is_active is False
        assert target_et.icon == new_icon_slug
        assert target_et.category.value == new_category_value
        assert target_et.updated_at > original_updated_at

        # Check response data with include_inactive because the event type is inactive now
        response_get = superuser_client.get(url, {"include_inactive": "true"})
        assert response_get.status_code == status.HTTP_200_OK
        response_data = response_get.data

        # Build expected response dictionary with all fields
        expected_response = {
            "id": str(target_et.id),
            "value": target_et.value,
            "display": new_display,
            "ordernum": target_et.ordernum,
            "category": new_category_value,
            "geometry_type": target_et.geometry_type,
            "default_priority": new_priority,
            "default_state": target_et.default_state,
            "resolve_time": target_et.resolve_time,
            "auto_resolve": target_et.auto_resolve,
            "readonly": target_et.readonly,
            "is_collection": target_et.is_collection,
            "is_active": False,
            "has_events_assigned": False,  # No events assigned since we just updated it
            "icon": new_icon_slug,
            "icon_id": new_icon_slug,
            "url": f"http://testserver/api/v2.0/activity/eventtypes/{target_et.value}/",
        }

        # Verify the response matches our expected dictionary
        assert response_data == expected_response

        # Verify the icon was actually updated in the database
        target_et.refresh_from_db()
        assert target_et.icon == new_icon_slug

    def test_patch_event_type_success(self, superuser_client, cat1_fire_v2_event_type):
        target_et = cat1_fire_v2_event_type
        original_icon_id = target_et.icon_id
        original_schema = target_et.schema
        original_updated_at = target_et.updated_at

        patch_payload = {
            "display": "Patched Display Name",
            "is_collection": not target_et.is_collection,  # Will become False
            "default_priority": PRI_URGENT,
        }

        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target_et.value})
        response = superuser_client.patch(url, data=patch_payload)

        assert response.status_code == status.HTTP_200_OK

        target_et.refresh_from_db()

        assert target_et.display == patch_payload["display"]
        assert target_et.is_collection == patch_payload["is_collection"]
        assert target_et.default_priority == patch_payload["default_priority"]
        assert target_et.updated_at > original_updated_at

        # Ensure other fields not in the payload are unchanged
        assert target_et.icon_id == original_icon_id
        assert target_et.schema == original_schema

        # Check response data
        response_get = superuser_client.get(url)
        assert response_get.status_code == status.HTTP_200_OK
        response_data = response_get.data
        assert response_data["display"] == patch_payload["display"]
        assert response_data["is_collection"] == patch_payload["is_collection"]
        assert response_data["default_priority"] == patch_payload["default_priority"]
        assert response_data["id"] == str(target_et.id)

    def test_patch_event_type_readonly_fields(self, superuser_client, cat1_fire_v2_event_type):
        """Test trying to update readonly fields (version, das_tenant)"""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        # Try to update version
        response = superuser_client.patch(url, data={"version": "1"})
        assert response.status_code == status.HTTP_200_OK
        cat1_fire_v2_event_type.refresh_from_db()
        assert cat1_fire_v2_event_type.version == "2"  # should remain unchanged

        # Try to update das_tenant
        response = superuser_client.patch(url, data={"das_tenant": "new_tenant"})
        assert response.status_code == status.HTTP_200_OK
        cat1_fire_v2_event_type.refresh_from_db()
        assert cat1_fire_v2_event_type.das_tenant_id is not None

    def test_patch_event_type_toggle_active(self, superuser_client, cat1_fire_v2_event_type):
        """Test that patching inactive EventType is supported"""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        # First make it inactive
        response = superuser_client.patch(url, data={"is_active": False})
        assert response.status_code == status.HTTP_200_OK

        cat1_fire_v2_event_type.refresh_from_db()
        assert cat1_fire_v2_event_type.is_active is False

        # Check that it is not found when not including inactive
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Then make it active again
        response = superuser_client.patch(url, data={"is_active": True})
        assert response.status_code == status.HTTP_200_OK
        cat1_fire_v2_event_type.refresh_from_db()
        assert cat1_fire_v2_event_type.is_active is True

        # Check that it is found now
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is True

    def test_patch_event_type_invalid_value_format(self, superuser_client, cat1_fire_v2_event_type):
        """Test updating with invalid value format (must match regex)"""
        invalid_value = "invalid!value"  # contains invalid character !
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        response = superuser_client.patch(url, data={"value": invalid_value})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "value" in response.data
        assert "invalid character" in str(response.data["value"][0])

    def test_patch_event_type_long_display(self, superuser_client, cat1_fire_v2_event_type):
        """Test updating with very long display name"""
        long_display = "hello" * 256  # exceeds max length of 255
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        response = superuser_client.patch(url, data={"display": long_display})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "display" in response.data
        assert "Ensure this field has no more than 255 characters" in str(response.data["display"][0])

    def test_patch_event_type_invalid_state(self, superuser_client, cat1_fire_v2_event_type):
        """Test updating with invalid state value"""
        invalid_state = "invalid_state"
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        response = superuser_client.patch(url, data={"default_state": invalid_state})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "default_state" in response.data
        assert "is not a valid choice" in str(response.data["default_state"][0])

    def test_patch_event_type_invalid_priority(self, superuser_client, cat1_fire_v2_event_type):
        """Test updating with invalid priority value"""
        invalid_priority = 999  # not in PRIORITY_CHOICES
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        response = superuser_client.patch(url, data={"default_priority": invalid_priority})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "default_priority" in response.data
        assert "is not a valid choice" in str(response.data["default_priority"][0])

    def test_delete_event_type_success(self, superuser_client, cat1_cat2_event_types):
        """
        Test deleting an EventType with no associated Events or Alerts.
        """
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        count_before = EventType.objects.count()

        response = superuser_client.delete(url)

        assert EventType.objects.count() == count_before - 1, "EventType count should decrease by 1"
        assert not EventType.objects.filter(pk=target.pk).exists(), "The specific EventType should no longer exist"
        # Assert 200 OK due to ExtendedJSONRenderer modifying 204 responses
        assert response.status_code == status.HTTP_200_OK
        expected_response = {
            "data": None,
            "status": {"code": status.HTTP_204_NO_CONTENT, "message": "No Content"},  # inconsistent with status code
        }
        assert response.json() == expected_response

    def test_delete_inactive_event_type(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[1]
        target.set_to_inactive()
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})

        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        response = superuser_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert not EventType.objects.filter(pk=target.pk).exists()

    def test_delete_event_type_success_after_cleaning_dependencies(
        self, superuser_client, superuser, cat1_cat2_event_types
    ):
        """
        Test deleting an EventType successfully after its dependencies (Event, AlertRule) have been removed via API.
        """
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        count_before = EventType.objects.count()

        # Create an Event
        event = Event.objects.create(event_type=target, created_by_user=superuser, title="Test Event 2")
        # Create an AlertRule
        alert_rule = AlertRule.objects.create(owner=superuser, title="Test Alert Rule 2")
        alert_rule.event_types.add(target)

        # Clean up dependencies through API
        event_url = reverse("event-view", kwargs={"id": event.id})
        delete_event_response = superuser_client.delete(event_url)
        assert delete_event_response.status_code == status.HTTP_200_OK

        alert_rule_url = reverse("alert-view", kwargs={"id": alert_rule.id})
        delete_alert_rule_response = superuser_client.delete(alert_rule_url)
        assert delete_alert_rule_response.status_code == status.HTTP_200_OK

        # Delete EventType
        response = superuser_client.delete(url)

        assert EventType.objects.count() == count_before - 1, "EventType count should decrease by 1"
        assert not EventType.objects.filter(pk=target.pk).exists(), "The specific EventType should no longer exist"
        assert response.status_code == status.HTTP_200_OK

    def test_delete_event_type_fail_with_event(self, superuser_client, cat1_cat2_event_types, superuser):
        """
        Test deleting an EventType associated with an Event fails.
        """
        target = cat1_cat2_event_types[0]
        # Create an Event linked to this EventType
        Event.objects.create(event_type=target, created_by_user=superuser, title="Test Event")

        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        count_before = EventType.objects.count()

        response = superuser_client.delete(url)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert EventType.objects.count() == count_before
        assert EventType.objects.filter(id=target.id).exists()
        assert "associated with existing Events" in response.data["detail"]
        assert "Alert Rules" not in response.data["detail"]  # Ensure only event reason is given

    def test_delete_event_type_fail_with_alert_rule(self, superuser_client, cat1_cat2_event_types, superuser):
        """
        Test deleting an EventType associated with an AlertRule fails.
        """
        target = cat1_cat2_event_types[1]
        # Create an AlertRule linked to this EventType
        alert_rule = AlertRule.objects.create(owner=superuser, title="Test Alert Rule")
        alert_rule.event_types.add(target)

        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        count_before = EventType.objects.count()

        response = superuser_client.delete(url)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert EventType.objects.count() == count_before
        assert EventType.objects.filter(id=target.id).exists()
        assert "associated with existing Alert Rules" in response.data["detail"]
        assert "Events" not in response.data["detail"]  # Ensure only alert reason is given

    def test_delete_event_type_fail_with_event_and_alert_rule(self, superuser_client, cat1_cat2_event_types, superuser):
        """
        Test deleting an EventType associated with both an Event and an AlertRule fails.
        """
        target = cat1_cat2_event_types[2]
        # Create an Event
        Event.objects.create(event_type=target, created_by_user=superuser, title="Test Event 2")
        # Create an AlertRule
        alert_rule = AlertRule.objects.create(owner=superuser, title="Test Alert Rule 2")
        alert_rule.event_types.add(target)

        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        count_before = EventType.objects.count()

        response = superuser_client.delete(url)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert EventType.objects.count() == count_before
        assert EventType.objects.filter(id=target.id).exists()
        # Check both reasons are in the message
        assert "associated with existing Events" in response.data["detail"]
        assert "associated with existing Alert Rules" in response.data["detail"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypesV2Schemas:
    """
    Tests for the EventTypesViewSet schemas.

    Tests:

    - Test that the list of event type schemas is returned successfully
    - Test that the schema of an event type is returned successfully
    """

    def test_get_event_type_schemas(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list-schemas")
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert len(response.data["results"]) > 0
        # For every active event type with an active category, its schema should be included
        active_event_types = {et.value for et in cat1_cat2_event_types if et.is_active}
        assert active_event_types == {i["value"] for i in response.data["results"]}

    def test_gracefully_fail_when_no_schema(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list-schemas")
        target = cat1_cat2_event_types[0]
        target.schema = ""
        target.save()
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_207_MULTI_STATUS

        target.schema = json.dumps({"ui": {}})
        target.save()
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_207_MULTI_STATUS

        target.schema = json.dumps({"json": {}, "ui": {}})
        target.save()
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_get_event_type_schema(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-retrieve-schema", kwargs={"eventtype_value": target.value})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_get_event_type_schema_with_dynamic_reference(self, superuser_client, cat1_cat2_event_types):
        """Test rendering a schema that references a dynamic schema endpoint"""
        # Setup an event type with a schema that references a dynamic schema
        target = cat1_cat2_event_types[0]
        subjects_schema_url = reverse("schemas:subjects")
        target.schema = json.dumps(
            {
                "ui": {},
                "json": {
                    "title": "Event Type Schema",
                    "type": "object",
                    "properties": {"subject": {"$ref": f"{subjects_schema_url}"}},
                },
            }
        )
        target.save()

        url = reverse("v2-eventtype-retrieve-schema", kwargs={"eventtype_value": target.value})
        # Test with pre_render=True
        response = superuser_client.get(url, {"pre_render": True})
        assert response.status_code == status.HTTP_200_OK
        assert "json" in response.data
        rendered_schema = response.data["json"]
        assert "properties" in rendered_schema
        assert "subject" in rendered_schema["properties"]
        assert "$ref" not in rendered_schema["properties"]["subject"]
        assert "oneOf" in rendered_schema["properties"]["subject"]

        # Test with pre_render=False
        response = superuser_client.get(url, {"pre_render": False})
        assert response.status_code == status.HTTP_200_OK
        assert "json" in response.data
        rendered_schema = response.data["json"]
        assert "properties" in rendered_schema
        assert "$ref" in rendered_schema["properties"]["subject"]
        assert "oneOf" not in rendered_schema["properties"]["subject"]

        # Test with pre_render=None (default)
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "json" in response.data
        rendered_schema = response.data["json"]
        assert "properties" in rendered_schema
        assert "$ref" in rendered_schema["properties"]["subject"]
        assert "oneOf" not in rendered_schema["properties"]["subject"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypesV2ConditionalResponses:
    """
    Tests for the conditional response headers (ETag, Last-Modified) in the EventTypesViewSet.

    Tests:

    - Test that the ETag header is included in the response
    - Test that the ETag header is updated when the list of event types changes
    - Test that the ETag header is updated when the list of event types changes or when filters are applied
    - Test that the ETag header is included in the response even when the response is empty
    - Test that the ETag header is included in the response for the detail of an event type
    - Test that the ETag header is updated when the detail of an event type changes

    """

    def test_list_response_includes_etag_header(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0
        assert response.has_header("ETag")

    def test_list_response_etag_header_is_updated(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        response1 = superuser_client.get(url)
        etag1 = response1.headers["ETag"]
        assert etag1 is not None

        # Test ETag is the same when no changes are made
        response2 = superuser_client.get(url)
        etag2 = response2.headers["ETag"]
        assert etag2 == etag1

        # Test ETag changes when fields are updated
        et = cat1_cat2_event_types[0]
        et.display = "Updated display"
        et.save()
        response2 = superuser_client.get(url)
        etag2 = response2.get("ETag")
        assert etag2 != etag1

        # Test ETag changes when filters are applied
        response3 = superuser_client.get(url, {"category": "cat1"})
        etag3 = response3.get("ETag")
        assert etag3 != etag1
        assert etag3 != etag2

    def test_list_conditional_response_if_none_match(self, user_client):
        """
        When the client sends an If-None-Match header matching the current ETag,
        the server should return a 304 Not Modified.
        """
        url = reverse("v2-eventtype-list")
        # First, obtain the current ETag from an initial request.
        response = user_client.get(url)
        etag = response.get("ETag")
        assert etag is not None

        # Now, simulate a conditional GET with that ETag.
        conditional_response = user_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert conditional_response.status_code == status.HTTP_304_NOT_MODIFIED

    def test_empty_list_response_response_has_etag(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url, {"category": "cat2", "is_collection": True})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0
        assert response.has_header("ETag")

    def test_event_type_detail_etag_header_is_updated(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        response1 = superuser_client.get(url)
        etag1 = response1.get("ETag")
        assert etag1 is not None

        # Test ETag is the same when no changes are made
        response2 = superuser_client.get(url)
        etag2 = response2.get("ETag")
        assert etag2 == etag1

        # Test ETag changes when fields are updated
        target.display = "Updated display"
        target.save()
        response2 = superuser_client.get(url)
        etag2 = response2.get("ETag")
        assert etag2 != etag1

    def test_event_type_detail_conditional_response_if_none_match(self, superuser_client, cat1_cat2_event_types):
        """
        For the detail endpoint, if the client sends a matching If-None-Match header,
        the response should be 304 Not Modified.
        """
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        response = superuser_client.get(url)
        etag = response.get("ETag")
        assert etag is not None

        conditional_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert conditional_response.status_code == status.HTTP_304_NOT_MODIFIED
