import json
import os
from typing import Any, NamedTuple

import pytest

from django.http import HttpResponseNotModified
from django.urls import reverse
from rest_framework import status

from activity.models import PRI_URGENT, SC_RESOLVED, EventCategory, EventType
from activity.tests import schema_examples
from activity.views import EventTypeView
from client_http import HTTPClient
from factories import EventTypeFactory

pytestmark = pytest.mark.django_db
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")

TEST_SCHEMA = json.dumps(
    {
        "schema": {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "EventType Test Schema for Updates",
            "type": "object",
            "properties": {
                "type_accident": {"type": "string", "title": "Type of accident"},
                "number_people_involved": {"type": "number", "title": "Number of people involved", "minimum": 0},
                "animals_involved": {"type": "string", "title": "Animals involved"},
            },
        },
        "definition": [
            {"key": "type_accident", "htmlClass": "col-lg-6"},
            {"key": "number_people_involved", "htmlClass": "col-lg-6"},
            {"key": "animals_involved", "htmlClass": "col-lg-6"},
        ],
    }
)


class EventTypeDetails(NamedTuple):
    eventtype: EventType
    user: Any


@pytest.fixture
def eventtype_fixture(db, django_user_model):
    EventType.objects.all().delete()
    EventCategory.objects.all().delete()

    event_category = EventCategory.objects.create(value="monitoring", display="Monitoring")
    EventCategory.objects.create(value="analyzer_event", display="Analyzer Event")

    event_type = EventType.objects.create(
        display="Wildlife Sighting",
        value="wildlife_sighting_rep",
        category=event_category,
        schema=schema_examples.WILDLIFE_SCHEMA,
    )

    user_const = dict(first_name="first", last_name="last")
    user = django_user_model.objects.create_user(
        "user", "user@test.com", "all_perms_user", is_superuser=True, is_staff=True, **user_const
    )

    return EventTypeDetails(eventtype=event_type, user=user)


EVENT_TYPE_UPDATES = (
    ("default_priority", PRI_URGENT),
    ("default_state", SC_RESOLVED),
    ("display", "A random display"),
    ("value", "a-random-value"),
    ("icon", "A broken icon value"),
    ("is_active", False),
    ("is_collection", True),
    ("schema", TEST_SCHEMA),
)


def test_get_eventtypes_without_schema(eventtype_fixture, client, memory_store_client_mock, tenant_response):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user
    client.force_login(user)
    url = reverse("eventtypes")
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0].get("schema") is None


def test_get_eventtype_with_schema(eventtype_fixture, client, memory_store_client_mock, tenant_response):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user

    client.force_login(user)
    url = reverse("eventtypes")
    url += "?include_schema=true"

    response = client.get(url)
    assert len(response.data) == 1
    assert response.data[0].get("schema") is not None


def test_post_eventtype(eventtype_fixture, client, monkeypatch, memory_store_client_mock, tenant_response):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user

    client.force_login(user)
    url = reverse("eventtypes")
    data = {"display": "Accoustic Detection", "value": "acoustic_detection", "category": "analyzer_event"}
    response = client.post(url, data=data)
    assert response.status_code == 201
    assert response.data.get("value") == "acoustic_detection"


def test_post_eventtype_with_schema(eventtype_fixture, client, memory_store_client_mock, tenant_response):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user

    client.force_login(user)
    url = reverse("eventtypes")
    schema = """
        {
        "schema":
            {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Simple Schema Report",

                "type": "object",
                "properties": {}
            },
        "defintion": []
        }
        """
    data = {
        "display": "Simple Report",
        "value": "simple_report",
        "category": "monitoring",
        "schema": schema_examples.ET_SCHEMA,
    }
    response = client.post(url, data=data)
    assert response.status_code == 201


def test_update_eventtype(eventtype_fixture, client, memory_store_client_mock, tenant_response):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user
    eventtype_id = str(eventtype.id)

    assert eventtype.value == "wildlife_sighting_rep"

    client.force_login(user)
    url = reverse("eventtype", kwargs={"eventtype_id": eventtype_id})
    patch_data = {"display": "Updated Display", "value": "update_display", "icon_id": "carcass_rep"}

    response = client.patch(url, data=json.dumps(patch_data), content_type="application/json")
    assert response.status_code == 200
    assert response.data.get("value") == "update_display"
    assert response.data.get("icon_id") == "carcass_rep"


def test_set_eventtype_to_inactive(eventtype_fixture, client, memory_store_client_mock, tenant_response):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user
    eventtype_id = str(eventtype.id)

    inactive_eventtype = EventType.objects.filter(is_active=False).count()
    assert inactive_eventtype == 0

    client.force_login(user)
    url = reverse("eventtype", kwargs={"eventtype_id": eventtype_id})
    response = client.delete(url)
    assert response.status_code == 204

    inactive_eventtype = EventType.objects.filter(is_active=False).count()
    assert inactive_eventtype == 1


def test_post_eventtype_with_bad_schema(eventtype_fixture, client, memory_store_client_mock, tenant_response):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user

    client.force_login(user)
    url = reverse("eventtypes")

    data = {
        "display": "Simple Report",
        "value": "simple_report",
        "category": "monitoring",
        "schema": schema_examples.BAD_SCHEMA,
    }
    response = client.post(url, data=data)
    assert "Invalid schema tag" in response.data.get("schema")[0]
    assert response.status_code == 400


def test_readonly_eventtype(eventtype_fixture, client, memory_store_client_mock, tenant_response):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user

    client.force_login(user)
    url = reverse("eventtypes")
    schema = """
        {
        "schema":
            {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Simple Schema Report",

                "type": "object",
                "readonly": true,
                "properties": {
                    "placeholder": {
                    "type": "string",
                    "title": "schema report"
                    }
                }
            },
        "defintion": []
        }
        """
    data = {"display": "Simple Report", "value": "simple_report", "category": "monitoring", "schema": schema}
    response = client.post(url, data=data)
    assert response.status_code == 201

    # get that specific eventtype.
    response = client.get(response.data.get("url"))
    assert response.status_code == 200
    assert response.data["readonly"]


@pytest.mark.django_db
class TestEventTypeAPI:
    @pytest.mark.parametrize(
        "mocked_geometry_type", (EventType.GeometryTypesChoices.POINT, EventType.GeometryTypesChoices.POLYGON)
    )
    def test_event_type_response_geometry_type(self, mocked_geometry_type):
        event_type_instance = EventTypeFactory.create(geometry_type=mocked_geometry_type)

        response = self._get_response(event_type_id=event_type_instance.id)

        assert response.status_code == 200

        assert response.data["geometry_type"] == mocked_geometry_type.value

    def test_response_includes_etag_and_last_modified_headers(self, superuser_client, five_event_types):
        event_type_id = str(five_event_types[0].id)
        url = reverse("eventtype", kwargs={"eventtype_id": event_type_id})

        response_with_info = superuser_client.get(url, HTTP_IF_NONE_MATCH='"non-matching-etag"')
        etag = response_with_info.headers["ETag"]
        last_modified = response_with_info.headers["Last-Modified"]
        empty_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert response_with_info.status_code == status.HTTP_200_OK
        assert etag == empty_response.headers["ETag"]
        assert last_modified == empty_response.headers["Last-Modified"]
        assert empty_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert isinstance(empty_response, HttpResponseNotModified)

    @pytest.mark.parametrize("field_update", EVENT_TYPE_UPDATES)
    def test_field_update_generates_new_etag_response_header(self, superuser_client, five_event_types, field_update):
        event_type = five_event_types[0]
        event_type_id = str(event_type.id)
        url = reverse("eventtype", kwargs={"eventtype_id": event_type_id})
        field_to_update, new_value = field_update

        original_response = superuser_client.get(url, HTTP_IF_NONE_MATCH='"non-matching-etag"')
        original_etag = original_response.headers["ETag"]
        setattr(event_type, field_to_update, new_value)
        event_type.save()
        modified_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=original_etag)
        modified_etag = modified_response.headers["ETag"]

        assert original_response.status_code == status.HTTP_200_OK
        assert modified_response.status_code == status.HTTP_200_OK
        assert original_etag != modified_etag

    def _get_response(self, event_type_id):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()

        url = reverse("eventtype", kwargs={"eventtype_id": event_type_id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)
        return EventTypeView.as_view()(request, eventtype_id=event_type_id)


@pytest.mark.django_db
class TestEventTypesAPI:
    def test_response_includes_etag_and_last_modified_headers(self, superuser_client, five_event_types):
        url = reverse("eventtypes")

        response_with_info = superuser_client.get(url, HTTP_IF_NONE_MATCH='"non-matching-etag"')
        etag = response_with_info.headers["ETag"]
        last_modified = response_with_info.headers["Last-Modified"]
        empty_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert response_with_info.status_code == status.HTTP_200_OK
        assert etag == empty_response.headers["ETag"]
        assert last_modified == empty_response.headers["Last-Modified"]
        assert empty_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert isinstance(empty_response, HttpResponseNotModified)

    @pytest.mark.parametrize("field_update", EVENT_TYPE_UPDATES)
    def test_field_update_generates_new_etag_response_header(self, superuser_client, five_event_types, field_update):
        event_type = five_event_types[0]
        url = reverse("eventtypes")
        field_to_update, new_value = field_update

        original_response = superuser_client.get(url, HTTP_IF_NONE_MATCH='"non-matching-etag"')
        original_etag = original_response.headers["ETag"]
        setattr(event_type, field_to_update, new_value)
        event_type.save()
        modified_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=original_etag)
        modified_etag = modified_response.headers["ETag"]

        assert original_response.status_code == status.HTTP_200_OK
        assert modified_response.status_code == status.HTTP_200_OK
        assert original_etag != modified_etag
