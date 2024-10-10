import hashlib
from unittest.mock import MagicMock

import pytest

from django.http import QueryDict

from activity.models import EventType, PatrolType
from activity.views.response_headers import (
    EVENT_TYPE_FIELDS_FOR_ETAG,
    PATROL_TYPE_FIELDS,
    EventTypeQueryset,
    build_etag_header,
    build_event_type_etag_header,
    build_event_types_etag_header,
    build_patrol_type_etag_header,
    build_patrol_type_last_modified_header,
    build_patrol_types_etag_header,
    build_patrol_types_last_modified_header,
    concatenate_fields_from_model,
    get_most_recent_update_datetime_by_queryset,
)
from utils.etags import get_hash_from_queryset


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestResponseHeaderBuilders:
    @pytest.fixture
    def empty_request(self, superuser):
        request = MagicMock()
        request.user = superuser
        request.GET = QueryDict()

        return request

    def test_build_patrol_type_etag_header(self, five_patrol_segment):
        patrol_type = PatrolType.objects.first()
        concatenated_fields = concatenate_fields_from_model(PATROL_TYPE_FIELDS, patrol_type)
        expected_etag = hashlib.md5(concatenated_fields.encode("utf-8")).hexdigest()

        etag = build_patrol_type_etag_header(id=str(patrol_type.id))

        assert expected_etag == etag

    def test_build_patrol_type_last_modified_header(self, five_patrol_segment):
        patrol_type = PatrolType.objects.first()

        last_modified = build_patrol_type_last_modified_header(id=str(patrol_type.id))

        assert patrol_type.updated_at == last_modified

    def test_build_patrol_types_etag_header(self, five_patrol_segment):
        individual_tags = [
            concatenate_fields_from_model(PATROL_TYPE_FIELDS, patrol_type) for patrol_type in PatrolType.objects.all()
        ]
        concatenated_etags = ":".join(individual_tags)
        expected_etag = hashlib.md5(concatenated_etags.encode("utf-8")).hexdigest()

        etag = build_patrol_types_etag_header()

        assert expected_etag == etag

    def test_build_patrol_types_last_modified_header(self, five_patrol_segment):
        expected_last_modified = PatrolType.objects.order_by("-updated_at").last().updated_at

        last_modified = build_patrol_types_last_modified_header()

        assert expected_last_modified == last_modified

    def test_build_event_types_etag_header(self, empty_request, five_event_types):
        queryset = EventTypeQueryset(empty_request.user, empty_request.GET).get_queryset()
        queryset = queryset.values(*EVENT_TYPE_FIELDS_FOR_ETAG)
        schemas = []
        for event_type in queryset:
            schemas.append(event_type["schema"])
        expected_etag = get_hash_from_queryset(request=empty_request, queryset=queryset, extra_salt=":".join(schemas))

        etag = build_event_types_etag_header(empty_request)

        assert expected_etag == etag

    @pytest.mark.parametrize(
        ("mocked_field", "mocked_value"),
        (
            ("display", "new_display_value"),
            ("is_active", False),
            ("flag", "new_flag"),
            ("updated_at", "2021-01-01T00:00:00Z"),
            ("value", "new_value"),
            ("ordernum", 300.5),
        ),
    )
    def test_build_event_types_etag_header_should_change_when_category_changes(
        self, mocked_field, mocked_value, empty_request, five_event_types
    ):
        queryset = EventTypeQueryset(empty_request.user, empty_request.GET).get_queryset()
        queryset = queryset.values(*EVENT_TYPE_FIELDS_FOR_ETAG)
        schemas = []
        for event_type in queryset:
            schemas.append(event_type["schema"])
        expected_etag = get_hash_from_queryset(request=empty_request, queryset=queryset, extra_salt=":".join(schemas))
        etag = build_event_types_etag_header(empty_request)

        assert expected_etag == etag

        five_event_types[0].category.ordernum = 300.5
        setattr(five_event_types[0].category, mocked_field, mocked_value)
        five_event_types[0].category.save(update_fields=[mocked_field])

        new_etag = build_event_types_etag_header(empty_request)
        assert etag != new_etag

    def test_build_event_type_etag_header(self, empty_request, five_event_types):
        event_type = five_event_types[0]
        queryset = EventTypeQueryset(empty_request.user, empty_request.GET).get_queryset()
        queryset = queryset.filter(id=event_type.id).values(*EVENT_TYPE_FIELDS_FOR_ETAG)
        expected_etag = get_hash_from_queryset(request=empty_request, queryset=queryset, extra_salt=event_type.schema)
        etag = build_event_type_etag_header(empty_request, eventtype_id=str(event_type.id))

        assert expected_etag == etag

    @pytest.mark.parametrize(
        ("mocked_field", "mocked_value"),
        (
            ("display", "new_display_value"),
            ("is_active", False),
            ("flag", "new_flag"),
            ("updated_at", "2021-01-01T00:00:00Z"),
            ("value", "new_value"),
            ("ordernum", 300.5),
        ),
    )
    def test_build_event_type_etag_header_should_change_when_category_changes(
        self, mocked_field, mocked_value, empty_request, five_event_types
    ):
        event_type = five_event_types[1]
        queryset = EventTypeQueryset(empty_request.user, empty_request.GET).get_queryset()
        queryset = queryset.filter(id=event_type.id).values(*EVENT_TYPE_FIELDS_FOR_ETAG)
        schemas = []
        for obj in queryset:
            schemas.append(obj["schema"])
        expected_etag = get_hash_from_queryset(request=empty_request, queryset=queryset, extra_salt=":".join(schemas))
        etag = build_event_type_etag_header(empty_request, eventtype_id=str(event_type.id))

        assert expected_etag == etag

        setattr(event_type.category, mocked_field, mocked_value)
        event_type.category.save(update_fields=[mocked_field])
        new_etag = build_event_type_etag_header(empty_request, eventtype_id=str(event_type.id))

        assert etag != new_etag

    def test_get_most_recent_updated_at(self, five_patrol_segment):
        last_patrol_type = PatrolType.objects.order_by("-updated_at").last()

        most_recent_update = get_most_recent_update_datetime_by_queryset(PatrolType.objects)

        assert last_patrol_type.updated_at == most_recent_update

    def test_concatenate_fields(self, event_type):
        event_type = EventType.objects.first()

        concatenated_fields = concatenate_fields_from_model(("display", "value"), event_type)

        assert f"{event_type.display}:{event_type.value}" == concatenated_fields

    def test_build_etag_header(self, five_patrol_segment):
        def entry_to_string(*args, **kwargs):
            return "entry"

        concatenated_fields = ":".join(["entry"] * PatrolType.objects.count())
        expected_etag = hashlib.md5(concatenated_fields.encode("utf-8")).hexdigest()

        etag = build_etag_header(entry_to_string, PatrolType.objects.all())

        assert expected_etag == etag

    def test_etag_is_not_none_when_queryset_is_empty(self):
        def entry_to_string(*args, **kwargs):
            return "entry"

        EventType.objects.all().delete()

        etag = build_etag_header(entry_to_string, EventType.objects.all())

        assert etag is not None

    def test_last_modified_is_none_when_queryset_is_empty(self):
        EventType.objects.all().delete()

        last_modified = get_most_recent_update_datetime_by_queryset(EventType.objects)

        assert last_modified is None
