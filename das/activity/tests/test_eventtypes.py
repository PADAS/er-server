import json
import os
from unittest.mock import patch
from urllib.parse import urlencode

import pytest

from django.db import connection
from django.http import HttpResponseNotModified
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status

from activity.models import PRI_URGENT, SC_RESOLVED, Event, EventCategory, EventType
from activity.tests import schema_examples
from activity.tests.helpers.schema_test_utils import V1SchemaBuilder
from activity.views import EventTypesView, EventTypeView
from client_http import HTTPClient
from core.utils import DirectoryIconFinder
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
def test_new_eventtype_is_v1_by_default(superuser_client):
    EventType.objects.all().delete()
    assert EventType.objects.count() == 0

    url = reverse("eventtypes")
    data = {"display": "Accoustic Detection", "value": "acoustic_detection", "category": "analyzer_event"}
    response = superuser_client.post(url, data=data)
    assert response.status_code == 201
    assert response.data.get("value") == "acoustic_detection"

    event_type = EventType.objects.get(value="acoustic_detection")
    assert event_type.version == EventType.VersionChoices.VERSION_1


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
@pytest.mark.parametrize(
    "schema_builder_method,schema_args,expected_readonly",
    [
        # Valid V1 schemas with readonly=true
        ("readonly_schema", {"readonly_value": True}, True),
        ("readonly_schema", {"readonly_value": "true"}, True),
        ("readonly_schema", {"readonly_value": "1"}, True),
        ("readonly_schema", {"readonly_value": "yes"}, True),
        # Valid V1 schemas with readonly=false
        ("readonly_schema", {"readonly_value": False}, False),
        ("readonly_schema", {"readonly_value": "false"}, False),
        ("readonly_schema", {"readonly_value": "no"}, False),
        # Schema without readonly property
        ("simple_field", {"field_name": "test", "field_type": "string"}, False),
        # Invalid schema formats
        ("invalid_schema", {"schema_type": "malformed_json"}, False),
        ("invalid_schema", {"schema_type": "no_schema_key"}, False),
        ("invalid_schema", {"schema_type": "empty_string"}, False),
        ("invalid_schema", {"schema_type": "missing_schema_wrapper"}, False),
    ],
    ids=[
        # Valid V1 schemas with readonly=true
        "readonly_true_bool",
        "readonly_true_string",
        "readonly_1_string",
        "readonly_yes_string",
        # Valid V1 schemas with readonly=false
        "readonly_false_bool",
        "readonly_false_string",
        "readonly_no_string",
        # Schema without readonly property
        "no_readonly_property",
        # Invalid schema formats
        "malformed_json",
        "no_schema_key",
        "empty_string",
        "missing_schema_wrapper",
    ],
)
def test_rendering_readonly_does_not_break_endpoints(
    superuser_client,
    five_event_categories,
    schema_builder_method,
    schema_args,
    expected_readonly,
):
    """Test that various V1 schema formats including malformed ones don't break the event types list endpoint.

    The readonly property is only used in V1 EventType schemas, not V2.
    This test ensures the is_schema_readonly method handles all V1 schema variations gracefully.
    """
    schema_builder = getattr(V1SchemaBuilder, schema_builder_method)
    schema_data = schema_builder(**schema_args)
    if isinstance(schema_data, dict):
        schema_data = json.dumps(schema_data)

    event_type = EventTypeFactory.create(
        category=five_event_categories[0],
        version=EventType.VersionChoices.VERSION_1,
        schema=schema_data,
        value=f"test_event_{expected_readonly}_{id(schema_args)}",
        display="Test V1 Event Type with Readonly",
    )

    # Test the list endpoint - this should not raise any exceptions
    url = reverse("eventtypes")
    response = superuser_client.get(url)
    assert response.status_code == 200

    # Find the created event type in the response
    event_type_data = None
    # response.data is a ReturnList for this endpoint (not paginated)
    for item in response.data:
        if item.get("id") == str(event_type.id):
            event_type_data = item
            break

    assert event_type_data is not None, "Event type not found in list response"

    # Check if readonly is set correctly based on schema
    if expected_readonly:
        assert event_type_data.get("readonly") is True
    else:
        # If readonly is false or not set, the field should not be in the response
        # or should be false (check implementation specifics)
        assert event_type_data.get("readonly") is None or event_type_data.get("readonly") is False

    # Test the detail endpoint as well
    detail_url = reverse("eventtype", kwargs={"eventtype_id": event_type.id})
    detail_response = superuser_client.get(detail_url)

    assert detail_response.status_code == 200

    # Check readonly in detail response
    if expected_readonly:
        assert detail_response.data.get("readonly") is True
    else:
        assert detail_response.data.get("readonly") is None or detail_response.data.get("readonly") is False


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

    def test_event_type_return_has_events_assigned(self, superuser_client, five_event_types):
        event_type_1, event_type_2, *_ = five_event_types
        Event.objects.create(event_type=event_type_1)

        url = reverse("eventtype", kwargs={"eventtype_id": event_type_1.id})
        response_event_type_1 = superuser_client.get(url)

        assert response_event_type_1.status_code == status.HTTP_200_OK
        assert response_event_type_1.data["has_events_assigned"] is True

        url = reverse("eventtype", kwargs={"eventtype_id": event_type_2.id})

        response_event_type_2 = superuser_client.get(url)

        assert response_event_type_2.status_code == status.HTTP_200_OK
        assert response_event_type_2.data["has_events_assigned"] is False


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

    def test_response_includes_only_v1_event_types(self, superuser_client, five_event_types, cat1_cat2_event_types):
        url = reverse("eventtypes")
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        response_ids = {et_data["id"] for et_data in response.data}
        v1_count = v2_count = 0

        for et in EventType.objects.filter(category__is_active=True, is_active=True):
            if et.version == EventType.VersionChoices.VERSION_1:
                assert str(et.id) in response_ids
                v1_count += 1
            else:
                assert str(et.id) not in response_ids
                v2_count += 1
        assert v1_count > 0
        assert v2_count == 4  # 4 active v2 event types in the cat1_cat2_event_types fixture

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

    def test_event_types_return_has_events_assigned(self, superuser_client, five_event_types):
        url = reverse("eventtypes")

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        for event_type in response.data:
            assert event_type["has_events_assigned"] is False

        for event_type in EventType.objects.all():
            Event.objects.create(event_type=event_type)

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        for event_type in response.data:
            assert event_type["has_events_assigned"] is True

    def test_event_type_database_hits(self, superuser_client, five_event_types):
        """Guard the eventtypes list query budget against per-event-type N+1 growth.

        Budget breakdown: ~8 baseline queries + 5 constant per-model version
        aggregates from ``schemas.etags.get_dynamic_schema_sources_version``
        (ERA-13553), plus small headroom. Those 5 aggregates (Users, Sources,
        Subjects, SpatialFeatures, EventTypes) are constant regardless of how many
        event types exist, so the budget still catches per-event-type N+1 growth.
        """
        url = reverse("eventtypes")

        with CaptureQueriesContext(connection) as queries_context:
            response = superuser_client.get(url)
            assert response.status_code == status.HTTP_200_OK
            assert len(queries_context.captured_queries) <= 15


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


@pytest.mark.django_db
class TestIconsListView:
    @patch("core.utils.staticfiles_storage")
    def test_list_response(self, mock_storage, superuser_client):
        mock_storage.listdir.return_value = ([], ["icon1.jpeg", "icon2.png"])
        mock_storage.get_modified_time.return_value = 1234567890

        url = reverse("eventtypes-list-icons")

        response = superuser_client.get(url)
        assert response.status_code == 200
        assert response.data == {"icon_ids": ["icon1.jpeg", "icon2.png"], "resources_path": "/static/sprite-src/"}
        assert response["ETag"] in response.headers.values()
        assert "ETag" in response.headers

    @patch("core.utils.staticfiles_storage")
    def test_304_not_modified(self, mock_storage, superuser_client):
        mock_storage.listdir.return_value = ([], ["icon1.jpeg"])
        mock_storage.get_modified_time.return_value = 1234567890

        url = reverse("eventtypes-list-icons")
        response = superuser_client.get(url)
        assert response.status_code == 200
        etag = response["ETag"]

        res = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert res.status_code == 304
        assert response["ETag"] == res["ETag"]


@pytest.mark.django_db
class TestIconDownloadView:
    def _url(self, icon_id):
        return reverse("eventtype-icon-download", kwargs={"icon_id": icon_id})

    @patch("activity.views.events.types.finders")
    def test_download_by_stem_returns_svg(self, mock_finders, superuser_client, tmp_path):
        icon_file = tmp_path / "test_icon.svg"
        icon_file.write_bytes(b"<svg/>")

        with patch.object(
            DirectoryIconFinder,
            "_file_metadata",
            new_callable=lambda: property(lambda self: (("test_icon.svg", None),)),
        ):
            mock_finders.find.return_value = str(icon_file)
            response = superuser_client.get(self._url("test_icon"))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/svg+xml"

    @patch("activity.views.events.types.finders")
    def test_svg_preferred_over_other_extensions(self, mock_finders, superuser_client, tmp_path):
        svg_file = tmp_path / "test_icon.svg"
        svg_file.write_bytes(b"<svg/>")

        with patch.object(
            DirectoryIconFinder,
            "_file_metadata",
            new_callable=lambda: property(lambda self: (("test_icon.png", None), ("test_icon.svg", None))),
        ):
            mock_finders.find.return_value = str(svg_file)
            response = superuser_client.get(self._url("test_icon"))

        assert response.status_code == status.HTTP_200_OK
        mock_finders.find.assert_called_once_with("sprite-src/test_icon.svg")

    @patch("activity.views.events.types.finders")
    def test_non_svg_returned_when_no_svg_available(self, mock_finders, superuser_client, tmp_path):
        png_file = tmp_path / "test_icon.png"
        png_file.write_bytes(b"\x89PNG")

        with patch.object(
            DirectoryIconFinder,
            "_file_metadata",
            new_callable=lambda: property(lambda self: (("test_icon.png", None),)),
        ):
            mock_finders.find.return_value = str(png_file)
            response = superuser_client.get(self._url("test_icon"))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/png"

    @patch("activity.views.events.types.finders")
    def test_download_unknown_icon_returns_404(self, mock_finders, superuser_client):
        with patch.object(DirectoryIconFinder, "_file_metadata", new_callable=lambda: property(lambda self: ())):
            response = superuser_client.get(self._url("nonexistent"))

        assert response.status_code == status.HTTP_404_NOT_FOUND
        mock_finders.find.assert_not_called()

    @patch("activity.views.events.types.finders")
    def test_download_returns_404_when_file_not_on_disk(self, mock_finders, superuser_client):
        with patch.object(
            DirectoryIconFinder, "_file_metadata", new_callable=lambda: property(lambda self: (("missing.svg", None),))
        ):
            mock_finders.find.return_value = None
            response = superuser_client.get(self._url("missing"))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_returns_401(self, client):
        response = client.get(self._url("some_icon"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@patch("core.utils.staticfiles_storage.listdir", side_effect=Exception("Filesystem error"))
def test_list_icons_view_error_handling(mock_storage, superuser_client):
    DirectoryIconFinder._instance = None
    DirectoryIconFinder._cache.clear()

    url = reverse("eventtypes-list-icons")
    response = superuser_client.get(url)

    assert response.status_code == 500
    assert response.json()["status"]["detail"] == "Filesystem error"
    assert "icon_ids" not in response.data


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestV1EndpointsRejectV2EventTypes:
    """V1 endpoints must not expose or mutate V2 event types.

    A V2 event type accessed via V1 serializer can silently corrupt its schema
    because the V1 serializer has no knowledge of the V2 schema structure.
    All write operations — and lookups that enable them — must return 404.
    """

    def _make_v2(self):
        return EventTypeFactory.create(version=EventType.VersionChoices.VERSION_2)

    def test_get_v2_event_type_via_v1_detail_returns_404(self, superuser_client):
        v2_et = self._make_v2()
        url = reverse("eventtype", kwargs={"eventtype_id": v2_et.id})
        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_patch_v2_event_type_via_v1_returns_404(self, superuser_client):
        v2_et = self._make_v2()
        url = reverse("eventtype", kwargs={"eventtype_id": v2_et.id})
        response = superuser_client.patch(
            url, data=json.dumps({"display": "Tampered"}), content_type="application/json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_put_v2_event_type_via_v1_returns_404(self, superuser_client):
        v2_et = self._make_v2()
        url = reverse("eventtype", kwargs={"eventtype_id": v2_et.id})
        response = superuser_client.put(
            url,
            data=json.dumps({"display": "Tampered", "value": v2_et.value, "category": v2_et.category.value}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_v2_event_type_via_v1_returns_404_and_leaves_it_active(self, superuser_client):
        v2_et = self._make_v2()
        url = reverse("eventtype", kwargs={"eventtype_id": v2_et.id})
        response = superuser_client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        v2_et.refresh_from_db()
        assert v2_et.is_active is True

    def test_rank_v2_event_type_via_v1_is_allowed(self, superuser_client):
        v2_et = self._make_v2()
        url = reverse("eventtype-ranking", kwargs={"eventtype_id": v2_et.id})
        response = superuser_client.post(url, {"before_key": None})
        assert response.status_code not in (status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN)

    def test_patch_does_not_corrupt_v2_schema(self, superuser_client):
        v2_et = self._make_v2()
        original_schema = v2_et.schema
        url = reverse("eventtype", kwargs={"eventtype_id": v2_et.id})
        superuser_client.patch(url, data=json.dumps({"display": "Tampered"}), content_type="application/json")
        v2_et.refresh_from_db()
        assert v2_et.schema == original_schema
