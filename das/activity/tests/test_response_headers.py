import hashlib
from unittest.mock import MagicMock

import pytest

from django.http import QueryDict

from activity.models import EventType, PatrolType
from activity.views.response_headers import (
    EVENT_TYPE_FIELDS,
    PATROL_TYPE_FIELDS,
    build_etag_header,
    build_event_type_etag_header,
    build_event_type_last_modified_header,
    build_event_types_etag_header,
    build_event_types_last_modified_header,
    build_patrol_type_etag_header,
    build_patrol_type_last_modified_header,
    build_patrol_types_etag_header,
    build_patrol_types_last_modified_header,
    concatenate_fields_from_model,
    get_most_recent_update_datetime_by_queryset,
    EventTypeQueryset
)
from factories import EventTypeFactory


@pytest.mark.django_db
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

    def test_build_event_types_etag_header(self, empty_request):
        EventType.objects.all().delete()
        EventTypeFactory.create_batch(5)
        individual_tags = [
            concatenate_fields_from_model(EVENT_TYPE_FIELDS, event_type)
            for event_type in EventTypeQueryset(empty_request.user, empty_request.GET).get_queryset()
        ]
        concatenated_etags = ":".join(individual_tags)
        expected_etag = hashlib.md5(concatenated_etags.encode("utf-8")).hexdigest()

        etag = build_event_types_etag_header(empty_request)

        assert expected_etag == etag

    def test_build_event_type_etag_header(self, empty_request, five_event_types):
        event_type = EventType.objects.first()
        concatenated_fields = concatenate_fields_from_model(EVENT_TYPE_FIELDS, event_type)
        expected_etag = hashlib.md5(concatenated_fields.encode("utf-8")).hexdigest()

        etag = build_event_type_etag_header(empty_request, eventtype_id=str(event_type.id))

        assert expected_etag == etag

    def test_build_event_type_last_modified_header(self, empty_request, five_event_types):
        event_type = EventType.objects.first()

        last_modified = build_event_type_last_modified_header(empty_request, eventtype_id=str(event_type.id))

        assert event_type.updated_at == last_modified

    def test_build_event_types_last_modified_header(self, empty_request, five_event_types):
        expected_last_modified = EventType.objects.order_by("-updated_at").last().updated_at

        last_modified = build_event_types_last_modified_header(empty_request)

        assert expected_last_modified == last_modified

    def test_get_most_recent_updated_at(self, five_patrol_segment):
        last_patrol_type = PatrolType.objects.order_by("-updated_at").last()

        most_recent_update = get_most_recent_update_datetime_by_queryset(PatrolType.objects)

        assert last_patrol_type.updated_at == most_recent_update

    def test_concatenate_fields(self, event_type):
        event_type = EventType.objects.first()

        concatenated_fields = concatenate_fields_from_model(("display", "value"), event_type)

        assert "Acoustic Detection:acoustic_detection" == concatenated_fields

    def test_build_etag_header(self, five_patrol_segment):
        def entry_to_string(*args, **kwargs):
            return "entry"

        concatenated_fields = ":".join(["entry"] * PatrolType.objects.count())
        expected_etag = hashlib.md5(concatenated_fields.encode("utf-8")).hexdigest()

        etag = build_etag_header(entry_to_string, PatrolType.objects.all())

        assert expected_etag == etag

    def test_etag_is_none_when_queryset_is_empty(self):
        def entry_to_string(*args, **kwargs):
            return "entry"

        EventType.objects.all().delete()

        etag = build_etag_header(entry_to_string, EventType.objects.all())

        assert etag is None

    def test_last_modified_is_none_when_queryset_is_empty(self):
        EventType.objects.all().delete()

        last_modified = get_most_recent_update_datetime_by_queryset(EventType.objects)

        assert last_modified is None
