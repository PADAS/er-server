import pytest

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from activity.models import Event, EventType


@pytest.mark.django_db
class TestEventTypesV2:
    """
    Tests for the EventTypesViewSet - V2 Event Types API.

    Some of these tests are relying on the `inital_data.json` fixture.

    Tests:

    - Test that the list of event types is returned successfully
    - Test that the list of event types does not include inactive event types
    - Test that the list of event types includes inactive event types when the include_inactive parameter is set
    - Test that the list of event types can be filtered by category
    - Test that the list of event types can be filtered by is_collection
    - Test that the list of event types can be filtered by updated_since
    - Test that the list of event types includes an ETag header
    - Test that the list of event types includes an ETag header even when the response is "empty"
    - Test that the ETag header is updated when the list of event types changes or when filters are applied
    - Test that the detail of an event type is returned successfully
    - Test that the ETag header of the detail of an event type is updated
    - Test "has_events_assigned" field in event type detail
    - Test that the list of event type schemas is returned successfully
    - Test that the schema of an event type is returned successfully

    Future tests:
    - schemas:
        - schema is rendered correctly (valid)
        - schema references are resolved
        - schema references are resolved with the correct user data
        - schema references that cannot be resolved are logged and ignored
        - schema is cached
        - schema cache is invalidated when the event type is updated
        - schema cache is invalidated when any of the event type's related objects are updated
        - schema cache is invalidated when related references are updated
        - schema cache is invalidated when the user's permissions change for the event type
        - schema cache is invalidated when the user's permissions change for the event category


    - permissions:
        - test_event_types_list_does_not_include_not_allowed_categories
        - test_event_type_detail_does_not_include_not_allowed_categories
        - test_etag_changes_when_allowed_categories_changes

    """

    def test_get_event_types_list(self, user_client):
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

        url = reverse("v2-eventtype-list")
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0
        for field in expected_fields:
            assert field in response.data[0]

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
        assert len(response.data) > 0
        for et in response.data:
            assert et["category"] == "cat1"
        # Filter by category "cat2"
        response = superuser_client.get(url, {"category": "cat2"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0
        for et in response.data:
            assert et["category"] == "cat2"

    def test_filter_event_types_by_is_collection(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        # Filter where is_collection is true
        response = superuser_client.get(url, {"is_collection": "true"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0
        for et in response.data:
            assert et["is_collection"] is True
        # Filter where is_collection is false
        response = superuser_client.get(url, {"is_collection": "false"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0
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

    def test_list_response_includes_etag_header(self, user_client):
        url = reverse("v2-eventtype-list")
        response = user_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0
        assert response.has_header("ETag")

    def test_empty_list_response_response_has_etag(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url, {"category": "cat2", "is_collection": True})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0
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

    def test_list_conditional_response_if_none_match(self, superuser_client, cat1_cat2_event_types):
        """
        When the client sends an If-None-Match header matching the current ETag,
        the server should return a 304 Not Modified.
        """
        url = reverse("v2-eventtype-list")
        # First, obtain the current ETag from an initial request.
        response = superuser_client.get(url)
        etag = response.get("ETag")
        assert etag is not None

        # Now, simulate a conditional GET with that ETag.
        conditional_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert conditional_response.status_code == status.HTTP_304_NOT_MODIFIED

    def test_list_conditional_response_if_modified_since(self, superuser_client, cat1_cat2_event_types):
        """
        If the client sends an If-Modified-Since header matching the current resource's
        last modification date, the server should return 304 Not Modified.
        """
        url = reverse("v2-eventtype-list")
        response = superuser_client.get(url)
        last_modified = response.get("Last-Modified")
        if not last_modified:
            pytest.skip("No Last-Modified header present in response")
        conditional_response = superuser_client.get(url, HTTP_IF_MODIFIED_SINCE=last_modified)
        assert conditional_response.status_code == status.HTTP_304_NOT_MODIFIED

    def test_get_event_type_detail(self, superuser_client, cat1_cat2_event_types):
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
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"value": target.value})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(target.id)
        assert response.data["value"] == target.value
        assert response.has_header("ETag")

        for field in expected_fields:
            assert field in response.data

    def test_event_type_detail_etag_header_is_updated(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-detail", kwargs={"value": target.value})
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
        url = reverse("v2-eventtype-detail", kwargs={"value": target.value})
        response = superuser_client.get(url)
        etag = response.get("ETag")
        assert etag is not None

        conditional_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert conditional_response.status_code == status.HTTP_304_NOT_MODIFIED

    def test_event_type_detail_has_events_assigned(self, superuser_client, cat1_cat2_event_types):
        # TODO: Test EventTypeSerializer.get_has_events_assigned method does not log any warning

        et_active = cat1_cat2_event_types[0]
        et_inactive = cat1_cat2_event_types[1]

        Event.objects.create(event_type=et_active)

        url = reverse("v2-eventtype-detail", kwargs={"value": et_active.value})
        response_event_type_1 = superuser_client.get(url)

        assert response_event_type_1.status_code == status.HTTP_200_OK
        assert response_event_type_1.data["has_events_assigned"] is True

        url = reverse("v2-eventtype-detail", kwargs={"value": et_inactive.value})
        response_event_type_2 = superuser_client.get(url)

        assert response_event_type_2.status_code == status.HTTP_200_OK
        assert response_event_type_2.data["has_events_assigned"] is False

    def test_get_event_type_schemas(self, superuser_client, cat1_cat2_event_types):
        url = reverse("v2-eventtype-list-schemas")
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # For every active event type with an active category, its schema should be included
        for et in cat1_cat2_event_types:
            if not et.is_active:
                continue
            assert et.value in response.data
            # FUTURE: assert response.data[et.value] == render_schema(et.schema, user=superuser_client.user)

    def test_get_event_type_schema(self, superuser_client, cat1_cat2_event_types):
        target = cat1_cat2_event_types[0]
        url = reverse("v2-eventtype-retrieve-schema", kwargs={"value": target.value})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # FUTURE: assert response.data == render_schema(target.schema, user=superuser_client.user)
