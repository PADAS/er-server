import json
from unittest.mock import PropertyMock, patch
from urllib.parse import urlencode

import pytest
from google.auth.exceptions import DefaultCredentialsError

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from activity.models import (
    CommunityInput,
    CommunityInputEvent,
    CommunityInputEventType,
    Event,
    EventType,
)
from activity.serializers import CommunityInputSerializer
from factories import EventFactory, EventTypeFactory, EventTypeV2Factory


@pytest.fixture
def event_type(db, five_event_categories):  # noqa: unused-parameter
    return EventTypeV2Factory.create(category=five_event_categories[0])


@pytest.fixture
def another_event_type(db, five_event_categories):  # noqa: unused-parameter
    return EventTypeV2Factory.create(category=five_event_categories[0])


@pytest.fixture
def community_input(event_type):
    ci = CommunityInput.objects.create(
        name="Test Community",
        value="test_community",
        is_active=True,
    )
    ci.event_types.add(event_type)
    return ci


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestV1EventTypesByCommunityInput:
    list_url = "eventtypes"

    @pytest.fixture
    def v1_event_type(self, five_event_categories):
        return EventTypeFactory.create(category=five_event_categories[0])

    @pytest.fixture
    def v2_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(category=five_event_categories[0])

    @pytest.fixture
    def community_input(self, v1_event_type, v2_event_type):
        ci = CommunityInput.objects.create(
            name="Mixed Survey",
            value="mixed_survey",
            is_active=True,
        )
        ci.event_types.add(v1_event_type)
        ci.event_types.add(v2_event_type)
        return ci

    def test_v1_api_excludes_v2_event_types(self, superuser_client, community_input, v1_event_type, v2_event_type):
        url = reverse(self.list_url)
        response = superuser_client.get(url, {"community_input": community_input.value})
        assert response.status_code == status.HTTP_200_OK
        returned_values = {et["value"] for et in response.data}
        assert v1_event_type.value in returned_values
        assert v2_event_type.value not in returned_values


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCommunityInputModel:
    def test_str(self, community_input):
        assert str(community_input) == "Test Community"

    def test_value_regex_valid(self):
        ci = CommunityInput(name="Valid", value="valid_value_123")
        ci.full_clean()  # should not raise

    def test_value_regex_rejects_spaces(self):
        ci = CommunityInput(name="Bad", value="has spaces")
        with pytest.raises(ValidationError):
            ci.full_clean()

    def test_value_regex_rejects_hyphens(self):
        ci = CommunityInput(name="Bad", value="has-hyphen")
        with pytest.raises(ValidationError):
            ci.full_clean()

    def test_value_unique_per_tenant(self, community_input):
        duplicate = CommunityInput(
            name="Other Name",
            value=community_input.value,
        )
        with pytest.raises(Exception):
            duplicate.save()

    def test_duplicate_community_input_event_type_raises(self, community_input, event_type):
        community_input.event_types.add(event_type)
        with pytest.raises(Exception):
            CommunityInputEventType.objects.create(community_input=community_input, event_type=event_type)

    def test_duplicate_community_input_event_raises(self, community_input, event_type):
        event = EventFactory.create(event_type=event_type)
        CommunityInputEvent.objects.create(community_input=community_input, event=event)
        with pytest.raises(Exception):
            CommunityInputEvent.objects.create(community_input=community_input, event=event)

    def test_event_types_optional(self):
        ci = CommunityInput.objects.create(
            name="No Types",
            value="no_types",
            is_active=True,
        )
        assert ci.event_types.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCommunityInputSerializer:
    def test_serializes_fields(self, community_input, event_type):
        data = CommunityInputSerializer(community_input).data
        assert data["name"] == "Test Community"
        assert data["value"] == "test_community"
        assert data["is_active"] is True
        assert event_type.value in data["event_types"]

    def test_id_is_read_only(self, community_input):
        data = CommunityInputSerializer(community_input).data
        assert "id" in data

    def test_event_types_as_slug_list(self, community_input, event_type):
        data = CommunityInputSerializer(community_input).data
        assert isinstance(data["event_types"], list)
        assert data["event_types"] == [event_type.value]

    def test_valid_create(self, event_type):
        payload = {
            "name": "New Input",
            "value": "new_input",
            "is_active": True,
            "event_types": [event_type.value],
        }
        serializer = CommunityInputSerializer(data=payload)
        assert serializer.is_valid(), serializer.errors
        ci = serializer.save()
        assert ci.name == "New Input"
        assert ci.event_types.count() == 1

    def test_invalid_value_format(self):
        payload = {
            "name": "Bad Value",
            "value": "bad value!",
            "is_active": True,
            "event_types": [],
        }
        serializer = CommunityInputSerializer(data=payload)
        assert not serializer.is_valid()
        assert "value" in serializer.errors


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCommunityInputAPI:
    list_url = "v2-community-list"
    detail_url = "v2-community-detail"

    def test_list(self, superuser_client, community_input):
        url = reverse(self.list_url)
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        values = [item["value"] for item in response.data]
        assert community_input.value in values

    def test_retrieve(self, superuser_client, community_input):
        url = reverse(self.detail_url, kwargs={"value": community_input.value})
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == community_input.name

    def test_create(self, superuser_client, event_type):
        url = reverse(self.list_url)
        payload = {
            "name": "API Created",
            "value": "api_created",
            "is_active": True,
            "event_types": [event_type.value],
        }
        response = superuser_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["value"] == "api_created"
        assert CommunityInput.objects.filter(value="api_created").exists()

    def test_create_invalid_value(self, superuser_client):
        url = reverse(self.list_url)
        payload = {
            "name": "Bad",
            "value": "bad value!",
            "is_active": True,
            "event_types": [],
        }
        response = superuser_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_partial_update(self, superuser_client, community_input):
        url = reverse(self.detail_url, kwargs={"value": community_input.value})
        response = superuser_client.patch(url, {"is_active": False}, format="json")
        assert response.status_code == status.HTTP_200_OK
        community_input.refresh_from_db()
        assert community_input.is_active is False

    def test_update(self, superuser_client, community_input, event_type, another_event_type):
        url = reverse(self.detail_url, kwargs={"value": community_input.value})
        payload = {
            "name": "Updated Name",
            "value": community_input.value,
            "is_active": True,
            "event_types": [event_type.value, another_event_type.value],
        }
        response = superuser_client.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        community_input.refresh_from_db()
        assert community_input.name == "Updated Name"
        assert community_input.event_types.count() == 2

    def test_delete(self, superuser_client, community_input):
        # ExtendedJSONRenderer converts 204 NO CONTENT -> 200 OK with wrapped body
        url = reverse(self.detail_url, kwargs={"value": community_input.value})
        response = superuser_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert not CommunityInput.objects.filter(value=community_input.value).exists()

    def test_unauthenticated_returns_401(self, client):
        url = reverse(self.list_url)
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_retrieve_active_returns_200(self, client, community_input):
        url = reverse(self.detail_url, kwargs={"value": community_input.value})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] == community_input.value

    def test_unauthenticated_retrieve_inactive_returns_404(self, client):
        inactive = CommunityInput.objects.create(name="Inactive", value="inactive_ci", is_active=False)
        url = reverse(self.detail_url, kwargs={"value": inactive.value})
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_list_returns_401(self, client):
        url = reverse(self.list_url)
        response = client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_create_returns_401(self, client):
        url = reverse(self.list_url)
        response = client.post(url, {"name": "New", "value": "new_ci", "is_active": True}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_update_returns_401(self, client, community_input):
        url = reverse(self.detail_url, kwargs={"value": community_input.value})
        response = client.patch(url, json.dumps({"name": "Hacked"}), content_type="application/json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_authenticated_non_admin_list_returns_403(self, user_client):
        url = reverse(self.list_url)
        response = user_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_authenticated_non_admin_create_returns_403(self, user_client, event_type):
        url = reverse(self.list_url)
        payload = {
            "name": "Should Be Blocked",
            "value": "blocked_ci",
            "is_active": True,
            "event_types": [event_type.value],
        }
        response = user_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not CommunityInput.objects.filter(value="blocked_ci").exists()

    def test_authenticated_non_admin_update_returns_403(self, user_client, community_input):
        url = reverse(self.detail_url, kwargs={"value": community_input.value})
        response = user_client.patch(url, {"name": "Hacked"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        community_input.refresh_from_db()
        assert community_input.name != "Hacked"

    def test_authenticated_non_admin_delete_returns_403(self, user_client, community_input):
        url = reverse(self.detail_url, kwargs={"value": community_input.value})
        response = user_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert CommunityInput.objects.filter(value=community_input.value).exists()

    def test_list_returns_expected_fields(self, superuser_client, community_input):
        url = reverse(self.list_url)
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        item = response.data[0]
        for field in ("id", "name", "value", "is_active", "event_types"):
            assert field in item

    def test_create_rejects_readonly_event_type(self, superuser_client, five_event_categories):
        readonly_et = EventTypeV2Factory.create(
            category=five_event_categories[0],
            readonly=True,
        )
        url = reverse(self.list_url)
        response = superuser_client.post(
            url,
            {"name": "Test", "value": "test_readonly", "is_active": True, "event_types": [readonly_et.value]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "event_types" in response.data

    def test_create_accepts_non_readonly_event_type(self, superuser_client, five_event_categories):
        writable_et = EventTypeV2Factory.create(
            category=five_event_categories[0],
            readonly=False,
        )
        url = reverse(self.list_url)
        response = superuser_client.post(
            url,
            {"name": "Test", "value": "test_writable", "is_active": True, "event_types": [writable_et.value]},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCommunityInputDetailPublic:
    @pytest.fixture
    def active_community_input(self, event_type):
        ci = CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)
        ci.event_types.add(event_type)
        return ci

    @pytest.fixture
    def inactive_community_input(self, event_type):
        ci = CommunityInput.objects.create(name="Inactive Survey", value="inactive_survey", is_active=False)
        ci.event_types.add(event_type)
        return ci

    def _url(self, value, trailing_slash=True):
        suffix = "/" if trailing_slash else ""
        return f"/api/v2.0/community/{value}{suffix}"

    def test_active_returns_200(self, client, active_community_input):
        response = client.get(self._url(active_community_input.value))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] == active_community_input.value

    def test_no_trailing_slash_returns_200(self, client, active_community_input):
        response = client.get(self._url(active_community_input.value, trailing_slash=False))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] == active_community_input.value

    def test_inactive_returns_404(self, client, inactive_community_input):
        response = client.get(self._url(inactive_community_input.value))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_returns_404(self, client):
        response = client.get(self._url("does_not_exist"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_expected_fields(self, client, active_community_input):
        response = client.get(self._url(active_community_input.value))
        assert response.status_code == status.HTTP_200_OK
        for field in ("id", "name", "value", "is_active", "event_types"):
            assert field in response.data


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypesByCommunityInput:
    @pytest.fixture
    def event_type(self, five_event_categories):
        return EventTypeV2Factory.create(category=five_event_categories[0])

    @pytest.fixture
    def other_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(category=five_event_categories[0])

    @pytest.fixture
    def active_community_input(self, event_type):
        ci = CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)
        ci.event_types.add(event_type)
        return ci

    @pytest.fixture
    def inactive_community_input(self, event_type):
        ci = CommunityInput.objects.create(name="Inactive Survey", value="inactive_survey", is_active=False)
        ci.event_types.add(event_type)
        return ci

    def _url(self, community_input_value):
        return reverse("community-eventtype-list", kwargs={"community_input_value": community_input_value})

    def test_returns_200_without_authentication(self, client, active_community_input):
        response = client.get(self._url(active_community_input.value))
        assert response.status_code == status.HTTP_200_OK

    def test_returns_only_community_input_event_types(
        self, client, active_community_input, event_type, other_event_type
    ):
        response = client.get(self._url(active_community_input.value))
        assert response.status_code == status.HTTP_200_OK
        returned_values = {et["value"] for et in response.data}
        assert event_type.value in returned_values
        assert other_event_type.value not in returned_values

    def test_unknown_community_input_returns_404(self, client):
        response = client.get(self._url("does_not_exist"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_inactive_community_input_returns_404(self, client, inactive_community_input):
        response = client.get(self._url(inactive_community_input.value))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_polygon_event_types_excluded(self, client, five_event_categories):
        polygon_et = EventTypeV2Factory.create(
            category=five_event_categories[0],
            geometry_type=EventType.GeometryTypesChoices.POLYGON,
        )
        point_et = EventTypeV2Factory.create(
            category=five_event_categories[0],
            geometry_type=EventType.GeometryTypesChoices.POINT,
        )
        ci = CommunityInput.objects.create(name="Geo Survey", value="geo_survey", is_active=True)
        ci.event_types.add(polygon_et, point_et)

        response = client.get(self._url(ci.value))

        assert response.status_code == status.HTTP_200_OK
        returned_values = {et["value"] for et in response.data}
        assert point_et.value in returned_values
        assert polygon_et.value not in returned_values


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypeRetrieveSchemaByCommunityInput:
    @pytest.fixture
    def event_type(self, five_event_categories):
        return EventTypeV2Factory.create(category=five_event_categories[0])

    @pytest.fixture
    def v1_event_type(self, five_event_categories):
        return EventTypeFactory.create(category=five_event_categories[0])

    @pytest.fixture
    def other_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(category=five_event_categories[0])

    @pytest.fixture
    def active_community_input(self, event_type):
        ci = CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)
        ci.event_types.add(event_type)
        return ci

    @pytest.fixture
    def inactive_community_input(self, event_type):
        ci = CommunityInput.objects.create(name="Inactive Survey", value="inactive_survey", is_active=False)
        ci.event_types.add(event_type)
        return ci

    def _url(self, community_input_value, event_type_value):
        return reverse(
            "community-eventtype-retrieve-schema",
            kwargs={"community_input_value": community_input_value, "eventtype_value": event_type_value},
        )

    def test_unauthenticated_with_associated_event_type_returns_200(self, client, active_community_input, event_type):
        response = client.get(self._url(active_community_input.value, event_type.value))
        assert response.status_code == status.HTTP_200_OK

    def test_v1_event_type_schema_returns_200(self, client, v1_event_type):
        ci = CommunityInput.objects.create(name="V1 Survey", value="v1_survey", is_active=True)
        ci.event_types.add(v1_event_type)
        response = client.get(self._url(ci.value, v1_event_type.value))
        assert response.status_code == status.HTTP_200_OK

    def test_event_type_not_in_community_input_returns_404(self, client, active_community_input, other_event_type):
        response = client.get(self._url(active_community_input.value, other_event_type.value))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_inactive_community_input_returns_404(self, client, inactive_community_input, event_type):
        response = client.get(self._url(inactive_community_input.value, event_type.value))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_community_input_returns_404(self, client, event_type):
        response = client.get(self._url("does_not_exist", event_type.value))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_with_pre_render_returns_200(self, client, active_community_input, event_type):
        response = client.get(self._url(active_community_input.value, event_type.value), {"pre_render": "true"})
        assert response.status_code == status.HTTP_200_OK

    def test_unauthenticated_with_pre_render_and_location_returns_200(self, client, active_community_input, event_type):
        response = client.get(
            self._url(active_community_input.value, event_type.value),
            {"pre_render": "true", "location": "0,0"},
        )
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCommunityInputEventCreation:
    @pytest.fixture
    def v2_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
        )

    @pytest.fixture
    def other_v2_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
        )

    @pytest.fixture
    def another_v2_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
        )

    @pytest.fixture
    def active_community_input(self, v2_event_type):
        ci = CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)
        ci.event_types.add(v2_event_type)
        return ci

    @pytest.fixture
    def inactive_community_input(self, v2_event_type):
        ci = CommunityInput.objects.create(name="Inactive Survey", value="inactive_survey", is_active=False)
        ci.event_types.add(v2_event_type)
        return ci

    def _url(self, community_input_value):
        return reverse("community-events", kwargs={"community_input_value": community_input_value})

    def _post(self, client, community_input_value, event_type_value):
        return client.post(
            self._url(community_input_value),
            json.dumps({"event_type": event_type_value}),
            content_type="application/json",
        )

    def test_form_encoded_post_returns_201(self, client, active_community_input, v2_event_type):
        response = client.post(
            self._url(active_community_input.value),
            urlencode({"event_type": v2_event_type.value}),
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_community_input_event_is_created_in_review_state(self, client, active_community_input, v2_event_type):
        response = self._post(client, active_community_input.value, v2_event_type.value)
        assert response.status_code == status.HTTP_201_CREATED
        event = Event.objects.get(id=response.data["id"])
        assert event.state == "review"

    def test_event_details_html_is_sanitized(self, client, active_community_input, v2_event_type):
        response = client.post(
            self._url(active_community_input.value),
            json.dumps(
                {
                    "event_type": v2_event_type.value,
                    "event_details": {
                        "species": "Lion",
                        "notes": "<script>alert(1)</script>danger",
                    },
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        event = Event.objects.get(id=response.data["id"])
        stored = event.event_details.first().data
        notes = stored.get("event_details", stored).get("notes", "")
        assert "<script>" not in notes
        assert "danger" in notes

    def test_state_in_payload_is_overridden_to_review(self, client, active_community_input, v2_event_type):
        response = client.post(
            self._url(active_community_input.value),
            json.dumps({"event_type": v2_event_type.value, "state": "active"}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        event = Event.objects.get(id=response.data["id"])
        assert event.state == "review"

    def test_created_at_in_payload_is_ignored(self, client, active_community_input, v2_event_type):
        backdate = "1970-01-01T00:00:00Z"
        response = client.post(
            self._url(active_community_input.value),
            json.dumps(
                {
                    "event_type": v2_event_type.value,
                    "created_at": backdate,
                    "updated_at": backdate,
                    "sort_at": backdate,
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        event = Event.objects.get(id=response.data["id"])
        assert event.created_at.year > 1970
        assert event.updated_at.year > 1970

    def test_related_subjects_in_payload_is_ignored(self, client, active_community_input, v2_event_type, subject):
        response = client.post(
            self._url(active_community_input.value),
            json.dumps({"event_type": v2_event_type.value, "related_subjects": [str(subject.id)]}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        event = Event.objects.get(id=response.data["id"])
        assert event.related_subjects.count() == 0

    def test_admin_only_fields_in_payload_are_ignored(self, client, active_community_input, v2_event_type):
        response = client.post(
            self._url(active_community_input.value),
            json.dumps(
                {
                    "event_type": v2_event_type.value,
                    "external_event_id": "attacker-supplied",
                    "attributes": {"injected": True},
                    "patrol_segments": [],
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        event = Event.objects.get(id=response.data["id"])
        # external_event_id flow requires both eventsource AND external_event_id;
        # neither field is on the public serializer, so no EventsourceEvent row.
        assert not event.eventsource_event_refs.exists()
        # attributes/patrol_segments are admin fields; ensure none were attached.
        assert event.patrol_segments.count() == 0

    def test_response_excludes_admin_only_fields(self, client, active_community_input, v2_event_type):
        response = client.post(
            self._url(active_community_input.value),
            json.dumps({"event_type": v2_event_type.value}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        # The narrow serializer's response shouldn't leak admin internals.
        for leaked in ("attributes", "patrol_segments", "eventsource", "external_event_id"):
            assert leaked not in response.data

    def test_invalid_community_input_returns_404(self, client, v2_event_type):
        response = self._post(client, "does_not_exist", v2_event_type.value)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_inactive_community_input_returns_404(self, client, inactive_community_input, v2_event_type):
        response = self._post(client, inactive_community_input.value, v2_event_type.value)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_event_type_not_in_community_input_returns_400(self, client, active_community_input, other_v2_event_type):
        response = self._post(client, active_community_input.value, other_v2_event_type.value)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_batch_with_disallowed_event_type_returns_400(
        self, client, active_community_input, v2_event_type, other_v2_event_type
    ):
        response = client.post(
            self._url(active_community_input.value),
            json.dumps(
                [
                    {"event_type": v2_event_type.value},
                    {"event_type": other_v2_event_type.value},
                ]
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_batch_with_mixed_event_types_returns_400(
        self, client, active_community_input, v2_event_type, another_v2_event_type
    ):
        active_community_input.event_types.add(another_v2_event_type)
        response = client.post(
            self._url(active_community_input.value),
            json.dumps(
                [
                    {"event_type": v2_event_type.value},
                    {"event_type": another_v2_event_type.value},
                ]
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_batch_with_same_allowed_event_type_returns_201(self, client, active_community_input, v2_event_type):
        response = client.post(
            self._url(active_community_input.value),
            json.dumps(
                [
                    {"event_type": v2_event_type.value},
                    {"event_type": v2_event_type.value},
                ]
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2

    def test_deleting_community_input_preserves_event(self, client, active_community_input, v2_event_type):
        response = self._post(client, active_community_input.value, v2_event_type.value)
        assert response.status_code == status.HTTP_201_CREATED
        event_id = response.data["id"]

        active_community_input.delete()

        assert Event.objects.filter(id=event_id).exists()
        assoc = CommunityInputEvent.objects.get(event_id=event_id)
        assert assoc.community_input is None


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventSchemaViewCommunityInput:
    @pytest.fixture
    def active_community_input(self):
        return CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)

    @pytest.fixture
    def inactive_community_input(self):
        return CommunityInput.objects.create(name="Inactive Survey", value="inactive_survey", is_active=False)

    def _url(self, community_input_value):
        return reverse("community-events-schema", kwargs={"community_input_value": community_input_value})

    def test_unauthenticated_with_active_community_input_returns_200(self, client, active_community_input):
        response = client.get(self._url(active_community_input.value))
        assert response.status_code == status.HTTP_200_OK

    def test_unknown_community_input_returns_404(self, client):
        response = client.get(self._url("does_not_exist"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_inactive_community_input_returns_404(self, client, inactive_community_input):
        response = client.get(self._url(inactive_community_input.value))
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCommunityInputEventNotes:
    @pytest.fixture
    def v2_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
        )

    @pytest.fixture
    def active_community_input(self, v2_event_type):
        ci = CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)
        ci.event_types.add(v2_event_type)
        return ci

    @pytest.fixture
    def inactive_community_input(self, v2_event_type):
        ci = CommunityInput.objects.create(name="Inactive Survey", value="inactive_survey", is_active=False)
        ci.event_types.add(v2_event_type)
        return ci

    @pytest.fixture
    def community_event(self, v2_event_type, active_community_input):
        event = EventFactory.create(event_type=v2_event_type)
        CommunityInputEvent.objects.create(community_input=active_community_input, event=event)
        return event

    @pytest.fixture
    def unrelated_event(self, v2_event_type):
        return EventFactory.create(event_type=v2_event_type)

    def _url(self, community_input_value, event_id):
        return reverse(
            "community-event-notes",
            kwargs={"community_input_value": community_input_value, "id": event_id},
        )

    def test_unauthenticated_post_returns_201(self, client, community_event, active_community_input):
        response = client.post(
            self._url(active_community_input.value, community_event.id),
            {"text": "A note from the public"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_inactive_community_input_returns_404(self, client, community_event, inactive_community_input):
        response = client.post(
            self._url(inactive_community_input.value, community_event.id),
            {"text": "Inactive CI"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_community_input_returns_404(self, client, community_event):
        response = client.post(
            self._url("does_not_exist", community_event.id),
            {"text": "Unknown CI"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_event_not_in_community_input_returns_403(self, client, unrelated_event, active_community_input):
        response = client.post(
            self._url(active_community_input.value, unrelated_event.id),
            {"text": "Event not linked to CI"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_returns_405(self, client, community_event, active_community_input):
        response = client.get(self._url(active_community_input.value, community_event.id))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCommunityInputEventFiles:
    @pytest.fixture
    def v2_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
        )

    @pytest.fixture
    def active_community_input(self, v2_event_type):
        ci = CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)
        ci.event_types.add(v2_event_type)
        return ci

    @pytest.fixture
    def inactive_community_input(self, v2_event_type):
        ci = CommunityInput.objects.create(name="Inactive Survey", value="inactive_survey", is_active=False)
        ci.event_types.add(v2_event_type)
        return ci

    @pytest.fixture
    def community_event(self, v2_event_type, active_community_input):
        event = EventFactory.create(event_type=v2_event_type)
        CommunityInputEvent.objects.create(community_input=active_community_input, event=event)
        return event

    @pytest.fixture
    def unrelated_event(self, v2_event_type):
        return EventFactory.create(event_type=v2_event_type)

    def _url(self, community_input_value, event_id):
        return reverse(
            "community-event-files",
            kwargs={"community_input_value": community_input_value, "id": event_id},
        )

    def test_unauthenticated_post_returns_201(self, anonymous_client, community_event, active_community_input):
        upload = SimpleUploadedFile("note.txt", b"community feedback", content_type="text/plain")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_inactive_community_input_returns_404(self, client, community_event, inactive_community_input):
        response = client.post(
            self._url(inactive_community_input.value, community_event.id),
            {},
            format="multipart",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_community_input_returns_404(self, client, community_event):
        response = client.post(
            self._url("does_not_exist", community_event.id),
            {},
            format="multipart",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_event_not_in_community_input_returns_403(self, client, unrelated_event, active_community_input):
        response = client.post(
            self._url(active_community_input.value, unrelated_event.id),
            {},
            format="multipart",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_returns_405(self, client, community_event, active_community_input):
        response = client.get(self._url(active_community_input.value, community_event.id))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_file_upload_with_missing_gcs_credentials_returns_503(
        self, anonymous_client, community_event, active_community_input
    ):
        upload = SimpleUploadedFile("note.txt", b"community feedback", content_type="text/plain")
        with patch(
            "django.core.files.storage.FileSystemStorage._save",
            side_effect=DefaultCredentialsError("Application Default Credentials not found"),
        ):
            response = anonymous_client.post(
                self._url(active_community_input.value, community_event.id),
                {"filecontent.file": upload},
                format="multipart",
            )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_oversized_upload_returns_413(
        self, anonymous_client, community_event, active_community_input, tenant_settings, monkeypatch
    ):
        tenant_settings.env_settings.community_input_max_upload_bytes = 10
        monkeypatch.setattr("activity.views.community_input_public.get_tenant_settings", lambda: tenant_settings)
        upload = SimpleUploadedFile("note.txt", b"this content exceeds ten bytes", content_type="text/plain")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    def test_upload_at_limit_returns_201(
        self, anonymous_client, community_event, active_community_input, tenant_settings, monkeypatch
    ):
        tenant_settings.env_settings.community_input_max_upload_bytes = 32
        monkeypatch.setattr("activity.views.community_input_public.get_tenant_settings", lambda: tenant_settings)
        upload = SimpleUploadedFile("note.txt", b"exactly under the limit content!", content_type="text/plain")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_disallowed_mime_returns_415(self, anonymous_client, community_event, active_community_input):
        upload = SimpleUploadedFile("payload.zip", b"PK\x03\x04 stub zip", content_type="application/zip")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    def test_octet_stream_returns_415(self, anonymous_client, community_event, active_community_input):
        upload = SimpleUploadedFile("blob.bin", b"\x00\x01\x02", content_type="application/octet-stream")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    def test_image_upload_returns_201(self, anonymous_client, community_event, active_community_input):
        upload = SimpleUploadedFile("photo.jpg", b"fake-jpeg-bytes", content_type="image/jpeg")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_pdf_upload_returns_201(self, anonymous_client, community_event, active_community_input):
        upload = SimpleUploadedFile("report.pdf", b"%PDF-1.4 stub", content_type="application/pdf")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_tenant_override_restricts_allowlist(
        self, anonymous_client, community_event, active_community_input, tenant_settings, monkeypatch
    ):
        tenant_settings.env_settings.community_input_allowed_mime_types = ["image/*"]
        monkeypatch.setattr("activity.views.community_input_public.get_tenant_settings", lambda: tenant_settings)
        pdf = SimpleUploadedFile("report.pdf", b"%PDF-1.4 stub", content_type="application/pdf")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": pdf},
            format="multipart",
        )
        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        image = SimpleUploadedFile("photo.jpg", b"fake-jpeg-bytes", content_type="image/jpeg")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": image},
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_default_allowlist_blocks_svg(self, anonymous_client, community_event, active_community_input):
        upload = SimpleUploadedFile(
            "vector.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            content_type="image/svg+xml",
        )
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    def test_real_jpeg_bytes_pass_sniff(self, anonymous_client, community_event, active_community_input):
        # FFD8FF is the JPEG magic prefix; filetype.guess returns image/jpeg.
        upload = SimpleUploadedFile(
            "photo.jpg",
            b"\xff\xd8\xff\xe0" + b"\x00" * 24,
            content_type="image/jpeg",
        )
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_pdf_bytes_declared_as_jpeg_returns_415(self, anonymous_client, community_event, active_community_input):
        upload = SimpleUploadedFile(
            "fake.jpg",
            b"%PDF-1.4\n" + b"\x00" * 50,
            content_type="image/jpeg",
        )
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    def test_tenant_override_can_extend_allowlist(
        self, anonymous_client, community_event, active_community_input, tenant_settings, monkeypatch
    ):
        tenant_settings.env_settings.community_input_allowed_mime_types = [
            "image/*",
            "application/zip",
        ]
        monkeypatch.setattr("activity.views.community_input_public.get_tenant_settings", lambda: tenant_settings)
        upload = SimpleUploadedFile("evidence.zip", b"PK\x03\x04 stub zip", content_type="application/zip")
        response = anonymous_client.post(
            self._url(active_community_input.value, community_event.id),
            {"filecontent.file": upload},
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestCommunityInputIconDownloadView:
    @pytest.fixture
    def active_community_input(self, event_type):
        ci = CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)
        ci.event_types.add(event_type)
        return ci

    @pytest.fixture
    def inactive_community_input(self, event_type):
        ci = CommunityInput.objects.create(name="Inactive Survey", value="inactive_survey", is_active=False)
        ci.event_types.add(event_type)
        return ci

    def _url(self, community_input_value, icon_id):
        from django.urls import reverse

        return reverse(
            "community-eventtype-icon-download",
            kwargs={"community_input_value": community_input_value, "icon_id": icon_id},
        )

    @patch("activity.views.events.types.finders")
    @patch("activity.views.events.types.DirectoryIconFinder._file_metadata", new_callable=PropertyMock)
    def test_returns_200_for_known_icon(self, mock_metadata, mock_finders, client, active_community_input, tmp_path):
        icon_file = tmp_path / "test_icon.svg"
        icon_file.write_bytes(b"<svg/>")
        mock_metadata.return_value = (("test_icon.svg", None),)
        mock_finders.find.return_value = str(icon_file)

        response = client.get(self._url(active_community_input.value, "test_icon"))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/svg+xml"

    @patch("activity.views.events.types.finders")
    @patch("activity.views.events.types.DirectoryIconFinder._file_metadata", new_callable=PropertyMock)
    def test_returns_404_for_unknown_icon(self, mock_metadata, mock_finders, client, active_community_input):
        mock_metadata.return_value = ()

        response = client.get(self._url(active_community_input.value, "nonexistent"))

        assert response.status_code == status.HTTP_404_NOT_FOUND
        mock_finders.find.assert_not_called()

    def test_inactive_community_input_returns_404(self, client, inactive_community_input):
        response = client.get(self._url(inactive_community_input.value, "any_icon"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_community_input_returns_404(self, client):
        response = client.get(self._url("does_not_exist", "any_icon"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("activity.views.events.types.finders")
    @patch("activity.views.events.types.DirectoryIconFinder._file_metadata", new_callable=PropertyMock)
    def test_no_trailing_slash_returns_200(self, mock_metadata, mock_finders, client, active_community_input, tmp_path):
        icon_file = tmp_path / "test_icon.svg"
        icon_file.write_bytes(b"<svg/>")
        mock_metadata.return_value = (("test_icon.svg", None),)
        mock_finders.find.return_value = str(icon_file)

        url = f"/api/v2.0/community/{active_community_input.value}/activity/events/eventtypes/icons/test_icon"
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK


_SCOPE_TO_ENV_FIELD = {
    "community_input_event": "community_input_event_throttle_rate",
    "community_input_file": "community_input_file_throttle_rate",
    "community_input_note": "community_input_note_throttle_rate",
    "community_input_read": "community_input_read_throttle_rate",
}


def _set_throttle_rates(tenant_settings, monkeypatch, **rates):
    """Set per-scope throttle rates on the tenant_settings env_settings and
    monkeypatch the view module's get_tenant_settings to return them.

    This is the canonical override path: rates live on the tenant, and the
    custom CommunityInputScopedThrottle reads them per-request.
    """
    for scope, rate in rates.items():
        setattr(tenant_settings.env_settings, _SCOPE_TO_ENV_FIELD[scope], rate)
    monkeypatch.setattr("activity.views.community_input_public.get_tenant_settings", lambda: tenant_settings)


@pytest.fixture
def clear_throttle_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "clear_throttle_cache")
class TestCommunityInputThrottling:
    @pytest.fixture
    def v2_event_type(self, five_event_categories):
        return EventTypeV2Factory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
        )

    @pytest.fixture
    def active_community_input(self, v2_event_type):
        ci = CommunityInput.objects.create(name="Active Survey", value="active_survey", is_active=True)
        ci.event_types.add(v2_event_type)
        return ci

    @pytest.fixture
    def community_event(self, v2_event_type, active_community_input):
        event = EventFactory.create(event_type=v2_event_type)
        CommunityInputEvent.objects.create(community_input=active_community_input, event=event)
        return event

    def _events_url(self, value):
        return reverse("community-events", kwargs={"community_input_value": value})

    def _files_url(self, value, event_id):
        return reverse("community-event-files", kwargs={"community_input_value": value, "id": event_id})

    def _notes_url(self, value, event_id):
        return reverse("community-event-notes", kwargs={"community_input_value": value, "id": event_id})

    def test_event_post_returns_429_after_rate_exceeded(
        self, client, active_community_input, v2_event_type, tenant_settings, monkeypatch
    ):
        _set_throttle_rates(tenant_settings, monkeypatch, community_input_event="1/hour")
        payload = json.dumps({"event_type": v2_event_type.value})
        r1 = client.post(self._events_url(active_community_input.value), payload, content_type="application/json")
        r2 = client.post(self._events_url(active_community_input.value), payload, content_type="application/json")
        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_file_post_returns_429_after_rate_exceeded(
        self, anonymous_client, active_community_input, community_event, tenant_settings, monkeypatch
    ):
        _set_throttle_rates(tenant_settings, monkeypatch, community_input_file="1/hour")
        url = self._files_url(active_community_input.value, community_event.id)
        r1 = anonymous_client.post(
            url,
            {"filecontent.file": SimpleUploadedFile("a.txt", b"a", content_type="text/plain")},
            format="multipart",
        )
        r2 = anonymous_client.post(
            url,
            {"filecontent.file": SimpleUploadedFile("b.txt", b"b", content_type="text/plain")},
            format="multipart",
        )
        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_note_post_returns_429_after_rate_exceeded(
        self, client, active_community_input, community_event, tenant_settings, monkeypatch
    ):
        _set_throttle_rates(tenant_settings, monkeypatch, community_input_note="1/hour")
        url = self._notes_url(active_community_input.value, community_event.id)
        r1 = client.post(url, {"text": "first"}, format="json")
        r2 = client.post(url, {"text": "second"}, format="json")
        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_scopes_are_isolated(self, client, active_community_input, v2_event_type, tenant_settings, monkeypatch):
        # Spending the event budget shouldn't affect the read budget.
        _set_throttle_rates(
            tenant_settings, monkeypatch, community_input_event="1/hour", community_input_read="60/hour"
        )
        payload = json.dumps({"event_type": v2_event_type.value})
        r1 = client.post(self._events_url(active_community_input.value), payload, content_type="application/json")
        r2 = client.post(self._events_url(active_community_input.value), payload, content_type="application/json")
        schema_url = reverse("community-events-schema", kwargs={"community_input_value": active_community_input.value})
        r3 = client.get(schema_url)
        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert r3.status_code == status.HTTP_200_OK
