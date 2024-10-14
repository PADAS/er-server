import json
import os
from urllib.parse import urlencode

import pytest

from django.http import HttpResponseNotModified
from django.urls import reverse
from rest_framework import status

from activity.models import PRI_URGENT, SC_RESOLVED, EventCategory, EventType
from activity.tests import schema_examples
from activity.views import EventTypesView, EventTypeView
from choices.models import Choice
from client_http import HTTPClient
from factories import EventTypeFactory
from utils.rank import RankedTool

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


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_post_eventtype(superuser_client, monkeypatch, tenant_document_cache_client_mock, tenant_response):
    EventType.objects.all().delete()
    url = reverse("eventtypes")
    data = {"display": "Accoustic Detection", "value": "acoustic_detection", "category": "analyzer_event"}
    response = superuser_client.post(url, data=data)
    assert response.status_code == 201
    assert response.data.get("value") == "acoustic_detection"


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_post_eventtype_with_schema(
    superuser_client, basic_event_categories, tenant_document_cache_client_mock, tenant_response
):
    EventType.objects.all().delete()
    url = reverse("eventtypes")
    data = {
        "display": "Simple Report",
        "value": "simple_report",
        "category": "monitoring",
        "schema": schema_examples.ET_SCHEMA,
    }
    response = superuser_client.post(url, data=data)
    assert response.status_code == 201


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_update_event_type(
    event_type, basic_event_categories, superuser_client, tenant_document_cache_client_mock, tenant_response
):
    event_category_monitoring = EventCategory.objects.get(value="monitoring")
    event_type.display = "Wildlife Sighting"
    event_type.value = "wildlife_sighting_rep"
    event_type.category = event_category_monitoring
    event_type.schema = schema_examples.WILDLIFE_SCHEMA
    event_type.save()
    patch_data = {"display": "Updated Display", "value": "update_display", "icon_id": "carcass_rep"}
    url = reverse("eventtype", kwargs={"eventtype_id": event_type.id})

    response = superuser_client.patch(url, data=json.dumps(patch_data), content_type="application/json")

    assert response.status_code == 200
    assert response.data.get("value") == "update_display"
    assert response.data.get("icon_id") == "carcass_rep"


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_set_eventtype_to_inactive(event_type, superuser_client, tenant_document_cache_client_mock, tenant_response):
    url = reverse("eventtype", kwargs={"eventtype_id": event_type.id})

    response = superuser_client.delete(url)

    assert response.status_code == 200
    assert EventType.objects.filter(is_active=False).count() == 1


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_post_eventtype_with_bad_schema(superuser_client, tenant_document_cache_client_mock, tenant_response):
    url = reverse("eventtypes")
    data = {
        "display": "Simple Report",
        "value": "simple_report",
        "category": "monitoring",
        "schema": schema_examples.BAD_SCHEMA,
    }

    response = superuser_client.post(url, data=data)

    assert "Invalid schema tag" in response.data.get("schema")[0]
    assert response.status_code == 400


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_readonly_eventtype(
    superuser_client, basic_event_categories, tenant_document_cache_client_mock, tenant_response
):
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

    response = superuser_client.post(url, data=data)
    response_detail = superuser_client.get(response.data.get("url"))

    assert response.status_code == 201
    assert response_detail.status_code == 200
    assert response_detail.data["readonly"]


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
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

    @pytest.mark.parametrize("field_update", EVENT_TYPE_UPDATES)
    def test_field_update_generates_new_etag_response_header(
        self, superuser_client, five_event_types, field_update, tenant_document_cache_client_mock
    ):
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

    def test_event_type_ranking_rank_second_as_first(self, superuser_client, five_event_types) -> None:
        qs = EventType.objects.all().order_by("ordernum", "value")
        RankedTool.make_full_rebalance(queryset=qs)
        event_type = list(qs)[1]

        url = reverse("eventtype-ranking", kwargs={"eventtype_id": str(event_type.id)})
        superuser_client.post(url, {"before_key": None})
        obj = EventType.objects.get(id=event_type.id)

        assert obj.ordernum == 0.5

    def test_event_type_change_category(self, superuser_client, event_type) -> None:
        new_event_category = EventCategory.objects.create(value="new_category", display="New Category", ordernum=1)

        url = reverse("eventtype-ranking", kwargs={"eventtype_id": str(event_type.id)})
        superuser_client.post(url, {"category_id": new_event_category.id})

        obj = EventType.objects.get(id=event_type.id)

        assert obj.category_id == new_event_category.id

    def test_event_type_rank_without_properties(self, superuser_client, event_type) -> None:
        url = reverse("eventtype-ranking", kwargs={"eventtype_id": str(event_type.id)})

        response = superuser_client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypesAPI:
    def test_response_includes_etag(self, superuser_client, five_event_types, tenant_document_cache_client_mock):
        url = reverse("eventtypes")

        response_with_info = superuser_client.get(url, HTTP_IF_NONE_MATCH='"non-matching-etag"')
        etag = response_with_info.headers["ETag"]
        empty_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert response_with_info.status_code == status.HTTP_200_OK
        assert etag == empty_response.headers["ETag"]

        assert empty_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert isinstance(empty_response, HttpResponseNotModified)

    def test_empty_response_includes_etag(self, superuser_client, five_event_types):
        base_url = reverse("eventtypes")
        qparams = {"category": 1, "is_collection": True, "is_active": False}
        url = f"{base_url}?{urlencode(qparams)}"
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert not len(response.data)
        assert "ETag" in response.headers
        assert len(response.headers["ETag"]) == 34

    @pytest.mark.parametrize("field_update", EVENT_TYPE_UPDATES)
    def test_field_update_generates_new_etag_response_header(
        self, superuser_client, five_event_types, field_update, tenant_document_cache_client_mock
    ):
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

    def test_schema_choices_update_generates_new_etag_response_header(self, superuser_client):
        EventType.objects.all().delete()
        EventCategory.objects.all().delete()

        monitoring_category = EventCategory.objects.create(value="monitoring", display="Monitoring")
        EventCategory.objects.create(value="analyzer_event", display="Analyzer Event")

        event_type = EventType.objects.create(
            display="Wildlife Sighting",
            value="wildlife_sighting_rep",
            category=monitoring_category,
            schema=schema_examples.WILDLIFE_SCHEMA,
        )

        url = reverse("eventtypes")
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert str(event_type.id) in [str(item.get("id")) for item in response.data]
        old_etag = response.headers["ETag"]
        assert len(old_etag) == 34  # ETags are MD5 hashes, 32 characters long, plus 2 quotes

        Choice.objects.create(
            **{
                "model": "activity.event",
                "field": "not_relevant_field",
                "value": "not_relevant_value",
                "display": "Not Relevant",
            }
        )
        response = superuser_client.get(url)
        new_etag = response.headers["ETag"]
        assert len(new_etag) == 34
        assert old_etag == new_etag

        Choice.objects.create(
            **{
                "model": "activity.event",
                "field": "wildlifesightingrep_species",
                "value": "zebra",
                "display": "Zebra",
            }
        )
        response = superuser_client.get(url)
        new_etag = response.headers["ETag"]
        assert old_etag != new_etag

    def test_filter_by_updated_since(self, superuser_client, five_event_categories):
        url = reverse("eventtypes")
        event_type = EventType(display="Initial Event", value="test", category=five_event_categories[0])
        event_type.save()
        updated_since = event_type.updated_at

        response_without_updated_since = superuser_client.get(url, HTTP_IF_NONE_MATCH='"non-matching-etag"')

        assert response_without_updated_since.status_code == status.HTTP_200_OK
        assert len(response_without_updated_since.data) == EventType.objects.all().count()

        response_with_updated_since = superuser_client.get(
            url, {"updated_since": updated_since}, HTTP_IF_NONE_MATCH='"non-matching-etag"'
        )

        assert response_with_updated_since.status_code == status.HTTP_200_OK
        assert len(response_with_updated_since.data) == 1

        assert response_with_updated_since.data[0]["id"] == str(event_type.id)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventTypeAutoResolve:

    @pytest.mark.parametrize(
        "data",
        [
            {"value": "test", "category": "security", "auto_resolve": False, "resolve_time": None},
            {"value": "test", "category": "security", "auto_resolve": True, "resolve_time": 5},
        ],
    )
    def test_create_event_type_with_auto_resolve_set(self, data, basic_event_categories):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()

        url = reverse("eventtypes")
        request = client.factory.post(url, data=data)
        client.force_authenticate(request, client.app_user)
        response = EventTypesView.as_view()(request)

        assert response.status_code == 201
        assert response.data["auto_resolve"] == data["auto_resolve"]
        assert response.data["resolve_time"] == data["resolve_time"]

    def test_get_event_type_with_auto_resolve(self, event_type):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()
        url = reverse("eventtype", kwargs={"eventtype_id": event_type.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        response = EventTypeView.as_view()(request, eventtype_id=event_type.id)

        assert "auto_resolve" in response.data
        assert "resolve_time" in response.data

    @pytest.mark.parametrize(
        "data",
        [
            {"auto_resolve": True, "resolve_time": 8},
            {"auto_resolve": False, "resolve_time": None},
        ],
    )
    def test_update_event_type_auto_resolve(self, data, event_type):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()

        url = reverse("eventtype", kwargs={"eventtype_id": event_type.id})
        request = client.factory.patch(url, data=data)
        client.force_authenticate(request, client.app_user)

        response = EventTypeView.as_view()(request, eventtype_id=event_type.id)

        assert response.status_code == 200
        assert response.data["auto_resolve"] == data["auto_resolve"]
        assert response.data["resolve_time"] == data["resolve_time"]

    def test_create_event_type_with_auto_resolve_true_and_not_resolve_time(self, basic_event_categories):
        data = {
            "value": "test",
            "category": "security",
            "auto_resolve": True,
        }
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()

        url = reverse("eventtypes")
        request = client.factory.post(url, data=data)
        client.force_authenticate(request, client.app_user)
        response = EventTypesView.as_view()(request)

        detail = response.data["status"]["detail"]
        assert response.status_code == 400
        assert "resolve_time" in detail
        assert "'resolve_time' must be set if 'auto_resolve' is true." in detail["resolve_time"]

    @pytest.mark.parametrize(
        "data",
        [
            {"auto_resolve": True, "resolve_time": None},
            {"auto_resolve": False, "resolve_time": 5},
        ],
    )
    def test_auto_resolve_test_update_event_type_auto_resolve_time_wrong(self, data, event_type):
        event_type.auto_resolve = True
        event_type.resolve_time = 5
        event_type.save()

        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()

        url = reverse("eventtype", kwargs={"eventtype_id": event_type.id})
        request = client.factory.patch(url, data=data)
        client.force_authenticate(request, client.app_user)
        response = EventTypeView.as_view()(request, eventtype_id=event_type.id)

        detail = response.data["status"]["detail"]
        assert response.status_code == 400
        assert "resolve_time" in detail
        assert (
            "'resolve_time' must be set if 'auto_resolve' is true." in detail["resolve_time"]
            or "'resolve_time' must be null if 'auto_resolve' is false." in detail["resolve_time"]
        )
