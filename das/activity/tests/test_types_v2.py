import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.models import PermissionSet
from activity.constants import PRI_IMPORTANT, PRI_URGENT
from activity.models import AlertRule, Event, EventType
from activity.schemas.migration.choice_processor import (
    HardcodedChoice,
    HardcodedChoiceResolution,
    ResolutionStrategy,
)
from activity.schemas.migration.service import MigrationResult
from activity.serializers.event_types_v2 import EventTypeV2Serializer
from activity.tests.helpers.schema_test_utils import (
    V2SchemaBuilder,
    minimal_event_type_schema,
)
from utils.categories import make_eventcategory_permission_codename_with_tenant


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

    @pytest.fixture
    def valid_schema(self):
        """Valid event type schema structure for tests."""
        return copy.deepcopy(minimal_event_type_schema)

    @pytest.fixture
    def base_post_data(self, valid_schema, cat1_cat2_categories):
        """Base POST data structure for event type creation."""
        return {
            "value": "test-event-type",
            "display": "Test Display",
            "category": cat1_cat2_categories[0].value,
            "schema": valid_schema,
        }

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

    def test_get_event_type_detail_create_only_permission(self, user_client, cat1_cat2_event_types, tenant_settings):
        target = cat1_cat2_event_types[0]
        target_category = target.category
        permission_set = PermissionSet.objects.create(name=f"test_perm_set_{target_category.value}")
        add_permission = Permission.objects.get(
            codename=make_eventcategory_permission_codename_with_tenant(
                target_category.value, "create", tenant_settings.id
            )
        )
        permission_set.permissions.add(add_permission)
        user_client.user.permission_sets.add(permission_set)

        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(target.id)
        assert response.data["value"] == target.value

        # Verify user cannot access event types from other categories
        cat2_event_type = [et for et in cat1_cat2_event_types if et.category.value == "cat2"][0]
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat2_event_type.value})
        response = user_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

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
        et_serializer = EventTypeV2Serializer()
        assert et_serializer.get_has_events_assigned(et_with_events) is True
        assert warning_msg in caplog.text

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

    @pytest.mark.parametrize(
        "json_schema_fixture",
        [
            "valid_nested_collection_schema.json",
            "valid_user_choices_schema.json",
            "valid_collection_field_w_description.json",
            "valid_event_type_v2_schema.json",
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

    def test_post_event_type_with_wrong_schema_draft(self, superuser_client, base_post_data):
        data = base_post_data.copy()
        url = reverse("v2-eventtype-list")
        data["schema"]["json"]["$schema"] = "https://json-schema.org/draft/-12/schema"
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # TODO: improve schema validation error response
        assert response.json() == {
            "schema": ["$schema must be https://json-schema.org/draft/2020-12/schema"],
            "status": {"code": 400, "message": "Bad Request"},
        }

    def test_post_event_type_missing_required_fields(self, superuser_client, cat1_cat2_categories, valid_schema):
        """Test POST validation for missing required fields."""
        url = reverse("v2-eventtype-list")

        # Test missing value field
        data = {
            "display": "Test Display",
            "category": cat1_cat2_categories[0].value,
            "schema": valid_schema,
        }
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "value" in response.data
        assert "This field is required." in response.data["value"][0]

        # Test missing category field
        data = {
            "value": "test-event-type",
            "display": "Test Display",
            "schema": valid_schema,
        }
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "category" in response.data
        assert "This field is required." in response.data["category"][0]

        # Test missing schema field
        data = {
            "value": "test-event-type",
            "display": "Test Display",
            "category": cat1_cat2_categories[0].value,
        }
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "schema" in response.data
        assert "This field is required." in response.data["schema"][0]

    def test_post_event_type_invalid_category(self, superuser_client, cat1_cat2_categories, valid_schema):
        """Test POST validation for invalid category value."""
        url = reverse("v2-eventtype-list")
        data = {
            "value": "test-event-type",
            "display": "Test Display",
            "category": "nonexistent-category",
            "schema": valid_schema,
        }
        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "category" in response.data
        assert "nonexistent-category does not exist" in response.data["category"][0]

    def test_post_event_type_invalid_value_format(self, superuser_client, cat1_cat2_categories, valid_schema):
        """Test POST validation for invalid value field format (regex validation)."""
        url = reverse("v2-eventtype-list")

        # Test value with spaces (invalid)
        data = {
            "value": "invalid value with spaces",
            "display": "Test Display",
            "category": cat1_cat2_categories[0].value,
            "schema": valid_schema,
        }
        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "value" in response.data
        assert "An invalid character was detected in the Event type Value field." in response.data["value"][0]

        # Test value with special characters (invalid)
        data["value"] = "invalid@value!"
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "value" in response.data
        assert "An invalid character was detected in the Event type Value field." in response.data["value"][0]

    def test_post_event_type_auto_resolve_constraint_violation(
        self, superuser_client, cat1_cat2_categories, valid_schema
    ):
        """Test POST validation for auto_resolve constraint violations."""
        url = reverse("v2-eventtype-list")

        # Test auto_resolve=True with resolve_time=None
        data = {
            "value": "test-event-type-1",
            "display": "Test Display",
            "category": cat1_cat2_categories[0].value,
            "auto_resolve": True,
            "resolve_time": None,
            "schema": valid_schema,
        }
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Check for the constraint validation error in the nested error format
        assert "resolve_time" in response.data.get("status", {}).get("detail", {})
        assert "'resolve_time' must be set if 'auto_resolve' is true." in (
            response.data["status"]["detail"]["resolve_time"]
        )

        # Test auto_resolve=False with resolve_time
        data.update({"auto_resolve": False, "resolve_time": 24})
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Check for the constraint validation error in the nested error format
        assert "resolve_time" in response.data.get("status", {}).get("detail", {})
        assert "'resolve_time' must be null if 'auto_resolve' is false." in (
            response.data["status"]["detail"]["resolve_time"]
        )

    def test_post_event_type_invalid_field_types(self, superuser_client, base_post_data):
        """Test POST validation for invalid field types."""
        url = reverse("v2-eventtype-list")

        # Test with invalid default_priority type
        data = base_post_data.copy()
        data.update({"default_priority": "invalid_priority_string"})
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "default_priority" in response.data
        assert '"invalid_priority_string" is not a valid choice' in response.data["default_priority"][0]

        # Test with invalid is_active type
        data = base_post_data.copy()
        data.update({"is_active": "not_a_boolean"})
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "is_active" in response.data
        assert "Must be a valid boolean." in response.data["is_active"][0]

        # Test with invalid readonly type
        data = base_post_data.copy()
        data.update({"readonly": "not_a_boolean"})
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "readonly" in response.data
        assert "Must be a valid boolean." in response.data["readonly"][0]

    def test_post_event_type_duplicate_value(self, superuser_client, cat1_fire_v2_event_type, base_post_data):
        """Test POST validation for duplicate value field."""
        url = reverse("v2-eventtype-list")
        data = base_post_data.copy()
        data.update({"value": cat1_fire_v2_event_type.value})  # Use existing event type value

        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        assert "__all__" in response.data["status"]["detail"]
        assert "Event Type with this Das tenant and Value already exists." in (
            response.data["status"]["detail"]["__all__"]
        )

    def test_post_event_type_readonly_field_attempts(self, superuser_client, cat1_cat2_categories, valid_schema):
        """Test that readonly fields are ignored in POST requests."""
        url = reverse("v2-eventtype-list")

        data = {
            "value": "test-readonly-event-type",
            "display": "Test Display",
            "category": cat1_cat2_categories[0].value,
            "schema": valid_schema,
            # Try to set readonly fields - these should be ignored
            "id": 99999,
            "version": "1",  # Should always be v2 for new event types
        }
        response = superuser_client.post(url, data=data)
        assert response.status_code == status.HTTP_201_CREATED

        # Verify readonly fields were ignored and set to correct values
        new_eventtype = EventType.objects.get(value=data["value"])
        assert new_eventtype.id != 99999  # ID should be auto-assigned
        assert new_eventtype.version == EventType.VersionChoices.VERSION_2  # Should be v2 for new types

        # Clean up the created event type
        new_eventtype.delete()

    # PUT tests
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

        assert response.status_code == status.HTTP_200_OK

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
            "url": f"http://testserver/api/v2.0/activity/eventtypes/{target_et.value}",
        }

        # Verify the response matches our expected dictionary
        assert response_data == expected_response

        # Verify the icon was actually updated in the database
        target_et.refresh_from_db()
        assert target_et.icon == new_icon_slug

    def test_put_event_type_missing_required_fields(self, superuser_client, cat1_fire_v2_event_type):
        """Test PUT validation for missing required fields."""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        # Test missing value field
        put_payload = {
            "display": "Test Display",
            "category": cat1_fire_v2_event_type.category.value,
            "schema": cat1_fire_v2_event_type.schema,
        }
        response = superuser_client.put(url, data=put_payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "value" in response.data
        assert "This field is required" in response.data["value"][0]

        # Test missing category field
        put_payload = {
            "value": "test-event-type",
            "display": "Test Display",
            "schema": cat1_fire_v2_event_type.schema,
        }
        response = superuser_client.put(url, data=put_payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "category" in response.data
        assert "This field is required" in response.data["category"][0]

    def test_put_event_type_invalid_category(self, superuser_client, cat1_fire_v2_event_type):
        """Test PUT validation for invalid category value."""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})
        put_payload = {
            "value": "test-event-type",
            "display": "Test Display",
            "category": "nonexistent-category",
            "default_priority": PRI_URGENT,
            "schema": cat1_fire_v2_event_type.schema,
        }
        response = superuser_client.put(url, data=put_payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "category" in response.data
        assert "Object with value=nonexistent-category does not exist." in response.data["category"][0]

    # PATCH tests
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

    def test_patch_event_type_auto_resolve_constraint_violation(self, superuser_client, cat1_fire_v2_event_type):
        """Test PATCH validation for auto_resolve constraint violations."""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        response = superuser_client.patch(url, data={"auto_resolve": True, "resolve_time": None})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "resolve_time" in response.data.get("status", {}).get("detail", {})
        assert "'resolve_time' must be set if 'auto_resolve' is true." in (
            response.data["status"]["detail"]["resolve_time"]
        )

        response = superuser_client.patch(url, data={"auto_resolve": False, "resolve_time": 24})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "resolve_time" in response.data.get("status", {}).get("detail", {})
        assert "'resolve_time' must be null if 'auto_resolve' is false." in (
            response.data["status"]["detail"]["resolve_time"]
        )

    def test_patch_event_type_duplicate_value(self, superuser_client, cat1_cat2_event_types):
        """Test PATCH validation for duplicate value field."""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_cat2_event_types[0].value})

        response = superuser_client.patch(url, data={"value": cat1_cat2_event_types[1].value})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "__all__" in response.data["status"]["detail"]
        assert "Event Type with this Das tenant and Value already exists." in (
            response.data["status"]["detail"]["__all__"]
        )

    def test_patch_event_type_invalid_value_format(self, superuser_client, cat1_fire_v2_event_type):
        """Test updating with invalid value format (must match regex)"""
        invalid_value = "invalid!value"  # contains invalid character !
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        response = superuser_client.patch(url, data={"value": invalid_value})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "value" in response.data
        assert "An invalid character was detected in the Event type Value field." in response.data["value"][0]

    def test_patch_event_type_long_display(self, superuser_client, cat1_fire_v2_event_type):
        """Test updating with very long display name"""
        long_display = "hello" * 256  # exceeds max length of 255
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        response = superuser_client.patch(url, data={"display": long_display})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "display" in response.data
        assert "Ensure this field has no more than 255 characters." in response.data["display"][0]

    def test_patch_event_type_invalid_category(self, superuser_client, cat1_fire_v2_event_type):
        """Test PATCH validation for invalid category value."""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        response = superuser_client.patch(url, data={"category": "nonexistent-category"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "category" in response.data
        assert "Object with value=nonexistent-category does not exist." in response.data["category"][0]

    def test_patch_event_type_invalid_field_types(self, superuser_client, cat1_fire_v2_event_type):
        """Test PATCH validation for invalid field types."""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        # Test with invalid default_priority type
        response = superuser_client.patch(url, data={"default_priority": "invalid_priority_string"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "default_priority" in response.data
        assert '"invalid_priority_string" is not a valid choice' in response.data["default_priority"][0]

        # Test with invalid state type
        response = superuser_client.patch(url, data={"default_state": "invalid_state"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "default_state" in response.data
        assert '"invalid_state" is not a valid choice.' in response.data["default_state"][0]

        # Test with invalid is_active type
        response = superuser_client.patch(url, data={"is_active": "not_a_boolean"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "is_active" in response.data
        assert "Must be a valid boolean." in response.data["is_active"][0]

        # Test with invalid readonly type
        response = superuser_client.patch(url, data={"readonly": "not_a_boolean"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "readonly" in response.data
        assert "Must be a valid boolean." in response.data["readonly"][0]

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
class TestEventTypesV2SchemaRendering:
    """
    Tests for the EventTypesViewSet schema endpoints:
    - /v2.0/activity/eventtypes/schemas/ (list of schemas)
    - /v2.0/activity/eventtypes/{eventtype_value}/schema/ (single schema)
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
class TestEventTypesV2Updates:
    """Tests for the EventType updates endpoint (revision history)."""

    def test_retrieve_updates_returns_revisions(self, superuser_client, cat1_fire_v2_event_type):
        """Test that the endpoint returns revisions for an EventType."""
        url = reverse("v2-eventtype-retrieve-updates", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, dict)
        assert len(response.data["results"]) == 1  # Only creation revision

        revision = response.data["results"][0]
        expected_fields = ["time", "action", "user", "updated_fields", "sequence"]
        for field in expected_fields:
            assert field in revision

    def test_retrieve_updates_after_schema_change(self, superuser_client, cat1_fire_v2_event_type):
        """Test revisions after schema field updates."""

        # Update schema
        new_schema = V2SchemaBuilder.simple_field("new_field", "string")
        cat1_fire_v2_event_type.schema = json.dumps(new_schema)
        cat1_fire_v2_event_type.save()

        # Verify new revision was created
        url = reverse("v2-eventtype-retrieve-updates", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

        # Find the schema update revision
        latest_revision = response.data["results"][0]
        assert latest_revision["action"] == "Updated"
        assert "schema" in latest_revision["updated_fields"]

    def test_retrieve_updates_multiple_changes(self, superuser_client, cat1_fire_v2_event_type):
        """Test multiple sequential updates create proper revision history."""
        url = reverse("v2-eventtype-retrieve-updates", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        # Make multiple changes
        changes = [
            {"field": "schema", "value": json.dumps(V2SchemaBuilder.simple_field("notes", "string"))},
            {"field": "display", "value": "Updated Display Name"},
            {"field": "default_priority", "value": Event.PRI_URGENT},
            {"field": "readonly", "value": True},  # Change from is_active to readonly to avoid filtering issues
        ]

        for change in changes:
            setattr(cat1_fire_v2_event_type, change["field"], change["value"])
            cat1_fire_v2_event_type.save()

        # Verify all revisions were created
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1 + len(changes)

        # Verify each change created a revision with the correct field
        recent_revisions = response.data["results"][: len(changes)]  # Get the most recent revisions
        updated_fields_from_revisions = []
        for revision in recent_revisions:
            assert revision["action"] == "Updated"
            updated_fields_from_revisions.extend(revision["updated_fields"])

        # Verify all changed fields appear in the revisions
        expected_fields = [change["field"] for change in changes]
        for field in expected_fields:
            assert field in updated_fields_from_revisions

    def test_retrieve_updates_nonexistent_eventtype(self, superuser_client):
        """Test 404 response for non-existent EventType."""
        url = reverse("v2-eventtype-retrieve-updates", kwargs={"eventtype_value": "nonexistent_type"})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "No EventType matches the given query" in str(response.data)

    def test_retrieve_updates_invalid_http_methods(self, superuser_client, cat1_fire_v2_event_type):
        """Test that only GET method is allowed on updates endpoint."""
        url = reverse("v2-eventtype-retrieve-updates", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        # Test unsupported methods
        methods_to_test = [
            (superuser_client.post, {"test": "data"}),
            (superuser_client.put, {"test": "data"}),
            (superuser_client.patch, {"test": "data"}),
            (superuser_client.delete, None),
        ]

        for method, data in methods_to_test:
            if data:
                response = method(url, data, format="json")
            else:
                response = method(url)
            assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


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


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestTrailingSlashConfiguration:
    """
    These tests verify that endpoints work both with and without trailing slashes in urls_v2.py.
    """

    def test_list_endpoint_with_and_without_trailing_slash(self, superuser_client):
        base_url = reverse("v2-eventtype-list")

        url_with_slash = f"{base_url}/" if not base_url.endswith("/") else base_url
        response_with_slash = superuser_client.get(url_with_slash)
        assert response_with_slash.status_code == status.HTTP_200_OK

        url_without_slash = base_url.rstrip("/")
        response_without_slash = superuser_client.get(url_without_slash)
        assert response_without_slash.status_code == status.HTTP_200_OK

        # Verify both responses return the same data
        assert response_with_slash.data == response_without_slash.data

    def test_detail_endpoint_with_and_without_trailing_slash(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[0]

        base_url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": target.value})

        url_with_slash = f"{base_url}/" if not base_url.endswith("/") else base_url
        response_with_slash = superuser_client.get(url_with_slash)
        assert response_with_slash.status_code == status.HTTP_200_OK

        url_without_slash = base_url.rstrip("/")
        response_without_slash = superuser_client.get(url_without_slash)
        assert response_without_slash.status_code == status.HTTP_200_OK

        # Verify both responses return the same data
        assert response_with_slash.data == response_without_slash.data


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestReadonlyExtractionFromSchema:
    """
    In V1, the 'readonly' property was stored inside the schema JSON. For V2, we now
    store it as a model field, but we still accept it in the schema for backwards
    compatibility with migrations from V1.
    """

    @pytest.fixture
    def valid_schema(self):
        """Valid event type schema structure for tests."""
        return copy.deepcopy(minimal_event_type_schema)

    def test_post_readonly_in_schema_sets_model_field(self, superuser_client, cat1_cat2_categories, valid_schema):
        """Test POST with 'readonly' in schema extracts it and sets the model field."""
        valid_schema["readonly"] = True
        data = {
            "value": "test-readonly-extraction",
            "display": "Test Readonly Extraction",
            "category": cat1_cat2_categories[0].value,
            "schema": valid_schema,
        }

        url = reverse("v2-eventtype-list")
        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_201_CREATED

        # Verify readonly is set on the model
        event_type = EventType.objects.get(value="test-readonly-extraction")
        assert event_type.readonly is True

        # Verify readonly is stripped from the stored schema
        stored_schema = json.loads(event_type.schema)
        assert "readonly" not in stored_schema

    def test_post_readonly_false_in_schema(self, superuser_client, cat1_cat2_categories, valid_schema):
        """Test POST with 'readonly': false in schema."""
        valid_schema["readonly"] = False
        data = {
            "value": "test-readonly-false",
            "display": "Test Readonly False",
            "category": cat1_cat2_categories[0].value,
            "schema": valid_schema,
        }

        url = reverse("v2-eventtype-list")
        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_201_CREATED

        event_type = EventType.objects.get(value="test-readonly-false")
        assert event_type.readonly is False

        stored_schema = json.loads(event_type.schema)
        assert "readonly" not in stored_schema

    def test_post_no_readonly_in_schema_uses_default(self, superuser_client, cat1_cat2_categories, valid_schema):
        """Test POST without 'readonly' in schema uses default model value."""
        data = {
            "value": "test-no-readonly",
            "display": "Test No Readonly",
            "category": cat1_cat2_categories[0].value,
            "schema": valid_schema,
        }

        url = reverse("v2-eventtype-list")
        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_201_CREATED

        event_type = EventType.objects.get(value="test-no-readonly")
        assert event_type.readonly is False  # Default value

    def test_patch_readonly_in_schema_updates_model(self, superuser_client, cat1_fire_v2_event_type):
        """Test PATCH with 'readonly' in schema updates the model field."""
        # First verify the event type has readonly=False
        assert cat1_fire_v2_event_type.readonly is False

        # Get current schema and add readonly
        current_schema = json.loads(cat1_fire_v2_event_type.schema)
        current_schema["readonly"] = True

        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})
        response = superuser_client.patch(url, data={"schema": current_schema})

        assert response.status_code == status.HTTP_200_OK

        cat1_fire_v2_event_type.refresh_from_db()
        assert cat1_fire_v2_event_type.readonly is True

        # Verify readonly is stripped from the stored schema
        stored_schema = json.loads(cat1_fire_v2_event_type.schema)
        assert "readonly" not in stored_schema

    def test_put_readonly_in_schema_updates_model(self, superuser_client, cat1_fire_v2_event_type):
        """Test PUT with 'readonly' in schema updates the model field."""
        url = reverse("v2-eventtype-detail", kwargs={"eventtype_value": cat1_fire_v2_event_type.value})

        # Get current data for PUT
        response_get = superuser_client.get(url, {"include_schema": "true"})
        put_payload = response_get.data.copy()

        # Remove read-only fields
        for fld in ["id", "url", "has_events_assigned", "icon_id"]:
            put_payload.pop(fld, None)

        # Add readonly to schema
        schema = put_payload["schema"]
        if isinstance(schema, str):
            schema = json.loads(schema)
        schema["readonly"] = True
        put_payload["schema"] = schema

        response = superuser_client.put(url, data=put_payload)
        assert response.status_code == status.HTTP_200_OK

        cat1_fire_v2_event_type.refresh_from_db()
        assert cat1_fire_v2_event_type.readonly is True

        stored_schema = json.loads(cat1_fire_v2_event_type.schema)
        assert "readonly" not in stored_schema

    def test_schema_readonly_overrides_body_readonly(self, superuser_client, cat1_cat2_categories, valid_schema):
        """Test that 'readonly' in schema takes precedence when both are provided."""
        valid_schema["readonly"] = True
        data = {
            "value": "test-readonly-precedence",
            "display": "Test Readonly Precedence",
            "category": cat1_cat2_categories[0].value,
            "schema": valid_schema,
            "readonly": False,  # Body says false, schema says true
        }

        url = reverse("v2-eventtype-list")
        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_201_CREATED

        event_type = EventType.objects.get(value="test-readonly-precedence")
        # Schema's readonly should take precedence
        assert event_type.readonly is True


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypeMigration:
    """Tests for the V1 to V2 schema migration endpoint."""

    @pytest.fixture
    def v1_event_type(self, cat1_cat2_categories):
        """Create a V1 EventType for migration testing."""
        from factories import EventTypeFactory

        category, _ = cat1_cat2_categories
        v1_schema = json.dumps(
            {
                "properties": {
                    "status": {
                        "type": "string",
                        "title": "Status",
                        "enum": ["open", "closed"],
                        "enumNames": ["Open", "Closed"],
                    },
                },
                "definition": ["status"],
            }
        )
        return EventTypeFactory.create(
            value="migration_test_v1",
            display="Migration Test V1",
            category=category,
            schema=v1_schema,
            version=EventType.VersionChoices.VERSION_1,
        )

    def test_migrate_dry_run_returns_preview(self, superuser_client, v1_event_type):
        """Test dry_run=true returns preview without persisting."""
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": True,
            "event_types": [v1_event_type.value],
        }

        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        results = response.data
        assert isinstance(results, list)
        assert len(results) == 1

        result = results[0]
        assert result["event_type"] == v1_event_type.value
        assert "v2_schema" in result
        assert "warnings" in result
        assert "errors" in result
        assert "metadata" in result

        # Verify not persisted
        v1_event_type.refresh_from_db()
        assert v1_event_type.version == EventType.VersionChoices.VERSION_1

    def test_migrate_without_dry_run_persists(self, superuser_client, v1_event_type):
        """Test dry_run=false persists the migration."""
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": False,
            "event_types": [v1_event_type.value],
        }

        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        result = response.data[0]

        # Check success (no errors)
        if not result["errors"]:
            v1_event_type.refresh_from_db()
            assert v1_event_type.version == EventType.VersionChoices.VERSION_2

    def test_migrate_nonexistent_event_type(self, superuser_client):
        """Test migration of non-existent event type returns error."""
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": True,
            "event_types": ["nonexistent_type"],
        }

        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        result = response.data[0]
        assert result["event_type"] == "nonexistent_type"
        assert len(result["errors"]) > 0
        assert "not found" in result["errors"][0]

    def test_migrate_multiple_event_types(self, superuser_client, v1_event_type, cat1_cat2_categories):
        """Test migrating multiple event types at once."""
        from factories import EventTypeFactory

        category, _ = cat1_cat2_categories
        v1_event_type_2 = EventTypeFactory.create(
            value="migration_test_v1_2",
            display="Migration Test V1 #2",
            category=category,
            schema="{}",
            version=EventType.VersionChoices.VERSION_1,
        )

        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": True,
            "event_types": [v1_event_type.value, v1_event_type_2.value],
        }

        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert response.data[0]["event_type"] == v1_event_type.value
        assert response.data[1]["event_type"] == v1_event_type_2.value

    def test_migrate_empty_event_types_returns_all_v1_preview(self, superuser_client, v1_event_type):
        """Test empty event_types list returns a dry-run preview for all V1 event types."""
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": True,
            "event_types": [],
        }

        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert any(result["event_type"] == v1_event_type.value for result in response.data)

        v1_event_type.refresh_from_db()
        assert v1_event_type.version == EventType.VersionChoices.VERSION_1

    @patch("activity.views.types_v2.MigrationService.migrate")
    def test_migrate_empty_event_types_requires_dry_run(self, mock_migrate, superuser_client):
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": False,
            "event_types": [],
        }

        response = superuser_client.post(url, data=data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["event_types"] == ["This list may not be empty when dry_run is false."]
        mock_migrate.assert_not_called()

    def test_migrate_missing_event_types_returns_400(self, superuser_client):
        """Test missing event_types field returns 400."""
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": True,
        }

        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_migrate_defaults_to_dry_run_true(self, superuser_client, v1_event_type):
        """Test that dry_run defaults to true when not specified."""
        url = reverse("v2-eventtype-migrate")
        data = {
            "event_types": [v1_event_type.value],
        }

        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK

        # Verify not persisted (dry_run should default to true)
        v1_event_type.refresh_from_db()
        assert v1_event_type.version == EventType.VersionChoices.VERSION_1

    def test_migrate_v2_event_type_returns_error(self, superuser_client, cat1_fire_v2_event_type):
        """Test migrating already-V2 event type returns error."""
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": True,
            "event_types": [cat1_fire_v2_event_type.value],
        }

        response = superuser_client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        result = response.data[0]
        assert len(result["errors"]) > 0
        assert "not V1" in result["errors"][0]

    @patch("activity.views.types_v2.MigrationService.migrate")
    def test_migrate_rejects_resolution_request_without_property_path(self, mock_migrate, superuser_client):
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": True,
            "event_types": [
                {
                    "event_type_value": "fire_rep",
                    "hardcoded_choices_resolutions": [
                        {
                            # missing property_path
                            "strategy": "USE_EXISTING",
                            "choice_field_name": "severity",
                        }
                    ],
                }
            ],
        }

        response = superuser_client.post(url, data=data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["event_types"][0]["hardcoded_choices_resolutions"][0]["property_path"] == [
            "This field is required."
        ]
        mock_migrate.assert_not_called()

    @patch("activity.views.types_v2.MigrationService.migrate")
    def test_migrate_accepts_structured_event_type_requests(self, mock_migrate, superuser_client):
        mock_migrate.return_value = [MigrationResult(event_type_value="fire_rep")]
        url = reverse("v2-eventtype-migrate")
        data = {
            "dry_run": True,
            "event_types": [
                {
                    "event_type_value": "fire_rep",
                    "hardcoded_choices_resolutions": [
                        {
                            "property_path": ["severity"],
                            "strategy": "USE_EXISTING",
                            "choice_field_name": "severity",
                        }
                    ],
                }
            ],
        }

        response = superuser_client.post(url, data=data, format="json")

        assert response.status_code == status.HTTP_200_OK
        event_types = mock_migrate.call_args.args[0]
        assert event_types[0]["event_type_value"] == "fire_rep"
        assert event_types[0]["hardcoded_choices_resolutions"][0]["property_path"] == ["severity"]
        assert event_types[0]["hardcoded_choices_resolutions"][0]["strategy"] == "USE_EXISTING"

    @patch("activity.views.types_v2.MigrationService.migrate")
    def test_migrate_response_includes_hardcoded_choices(self, mock_migrate, superuser_client):
        mock_migrate.return_value = [
            MigrationResult(
                event_type_value="fire_rep",
                v2_schema={"json": {"properties": {}}},
                hardcoded_choices=[
                    HardcodedChoice(
                        property_path=["severity"],
                        choices=[{"value": "minor", "display": "Minor"}],
                        resolution_options=[
                            HardcodedChoiceResolution(
                                property_path=["severity"],
                                strategy=ResolutionStrategy.CREATE_NEW,
                                choice_field_name="severity",
                            )
                        ],
                    )
                ],
            )
        ]
        url = reverse("v2-eventtype-migrate")

        response = superuser_client.post(url, data={"dry_run": True, "event_types": ["fire_rep"]}, format="json")

        assert response.status_code == status.HTTP_200_OK
        payload = response.data[0]
        assert payload["hardcoded_choices"][0]["property_path"] == ["severity"]
        assert payload["hardcoded_choices"][0]["choices"][0]["value"] == "minor"
        assert payload["hardcoded_choices"][0]["resolution_options"][0]["strategy"] == "CREATE_NEW"
