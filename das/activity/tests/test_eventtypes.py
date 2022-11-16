import json
import os
from typing import Any, NamedTuple
import pytest
from django.urls import reverse
from activity.models import EventCategory, EventType
from activity.tests import schema_examples
from activity.views import EventTypeView
from client_http import HTTPClient
from factories import EventTypeFactory

pytestmark = pytest.mark.django_db
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")


class EventTypeDetails(NamedTuple):
    eventtype: EventType
    user: Any


@pytest.fixture
def eventtype_fixture(db, django_user_model):
    EventType.objects.all().delete()
    EventCategory.objects.all().delete()

    event_category = EventCategory.objects.create(
        value="monitoring", display="Monitoring")
    EventCategory.objects.create(
        value="analyzer_event", display="Analyzer Event")

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


def test_get_eventtypes_without_schema(eventtype_fixture, client):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user

    client.force_login(user)
    url = reverse("eventtypes")
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0].get("schema") is None


def test_get_eventtype_with_schema(eventtype_fixture, client):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user

    client.force_login(user)
    url = reverse("eventtypes")
    url += "?include_schema=true"

    response = client.get(url)
    assert len(response.data) == 1
    assert response.data[0].get("schema") is not None


def test_post_eventtype(eventtype_fixture, client):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user

    client.force_login(user)
    url = reverse("eventtypes")
    data = {"display": "Accoustic Detection",
            "value": "acoustic_detection", "category": "analyzer_event"}
    response = client.post(url, data=data)
    assert response.status_code == 201
    assert response.data.get("value") == "acoustic_detection"


def test_post_eventtype_with_schema(eventtype_fixture, client):
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


def test_update_eventtype(eventtype_fixture, client):
    eventtype, user = eventtype_fixture.eventtype, eventtype_fixture.user
    eventtype_id = str(eventtype.id)

    assert eventtype.value == "wildlife_sighting_rep"

    client.force_login(user)
    url = reverse("eventtype", kwargs={"eventtype_id": eventtype_id})
    patch_data = {"display": "Updated Display",
                  "value": "update_display", "icon_id": "carcass_rep"}

    response = client.patch(url, data=json.dumps(
        patch_data), content_type="application/json")
    assert response.status_code == 200
    assert response.data.get("value") == "update_display"
    assert response.data.get("icon_id") == "carcass_rep"


def test_set_eventtype_to_inactive(eventtype_fixture, client):
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


def test_post_eventtype_with_bad_schema(eventtype_fixture, client):
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


def test_readonly_eventtype(eventtype_fixture, client):
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
    data = {"display": "Simple Report", "value": "simple_report",
            "category": "monitoring", "schema": schema}
    response = client.post(url, data=data)
    assert response.status_code == 201

    # get that specific eventtype.
    response = client.get(response.data.get("url"))
    assert response.status_code == 200
    assert response.data["readonly"]


class TestEventTypeAPI:
    @pytest.mark.parametrize(
        "mocked_geometry_type", (EventType.GeometryTypesChoices.POINT,
                                 EventType.GeometryTypesChoices.POLYGON)
    )
    def test_event_type_response_geometry_type(self, mocked_geometry_type):
        event_type_instance = EventTypeFactory.create(
            geometry_type=mocked_geometry_type)

        response = self._get_response(event_type_id=event_type_instance.id)

        assert response.status_code == 200

        assert response.data["geometry_type"] == mocked_geometry_type.value

    def _get_response(self, event_type_id):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()

        url = reverse("eventtype", kwargs={"eventtype_id": event_type_id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)
        return EventTypeView.as_view()(request, eventtype_id=event_type_id)
