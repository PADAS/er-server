import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from django.core.cache import cache
from django.http import QueryDict

from activity.models import EventType, PatrolType
from activity.serializers import EventTypeSerializer
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
from choices.models import Choice
from factories import EventTypeFactory
from utils.etags import get_hash_from_queryset
from utils.schema_utils import get_schema_renderer_method


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

        etag = build_event_types_etag_header(empty_request)

        five_event_types[0].category.ordernum = 300.5
        setattr(five_event_types[0].category, mocked_field, mocked_value)
        five_event_types[0].category.save(update_fields=[mocked_field])

        new_etag = build_event_types_etag_header(empty_request)
        assert etag != new_etag

    def test_build_event_type_etag_header(self, empty_request, five_event_types):
        event_type = five_event_types[0]
        queryset = EventTypeQueryset(empty_request.user, empty_request.GET).get_queryset()
        queryset = queryset.filter(id=event_type.id).values(*EVENT_TYPE_FIELDS_FOR_ETAG)
        schema_renderer = get_schema_renderer_method(event_type.schema)
        rendered_schema = schema_renderer(event_type.schema)
        hashed_schema = hashlib.md5(rendered_schema.encode("utf-8")).hexdigest()
        expected_etag = get_hash_from_queryset(request=empty_request, queryset=queryset, extra_salt=hashed_schema)
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

        etag = build_event_type_etag_header(empty_request, eventtype_id=str(event_type.id))

        assert etag

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

    def test_build_event_types_etag_header_should_change_when_choice_changes(
        self, empty_request, five_event_types, five_choices
    ):
        """Test that the ETag changes when a choice referenced in an eventtype schema is updated and cache is cleared."""

        # Create an eventtype with a schema that references choices
        event_type = five_event_types[0]
        schema_with_choices = {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Test Event Type",
                "type": "object",
                "properties": {
                    "species": {
                        "type": "string",
                        "title": "Species",
                        "enum": "{{enum___species___values}}",
                        "enumNames": "{{enum___species___names}}",
                    }
                },
            },
            "definition": ["species"],
        }
        event_type.schema = json.dumps(schema_with_choices)
        event_type.schema = event_type.schema.replace('"{{', "{{").replace('}}"', "}}")
        event_type.save(update_fields=["schema"])

        # Create choices for the species field
        choice1 = Choice.objects.create(
            model="activity.event", field="species", value="lion", display="Lion", ordernum=1
        )
        Choice.objects.create(model="activity.event", field="species", value="elephant", display="Elephant", ordernum=2)

        # Get the initial ETag
        initial_etag = build_event_types_etag_header(empty_request)

        # Update one of the choices
        # Note: Don't use update_fields here because it bypasses auto_now fields
        choice1.display = "African Lion"
        choice1.save()

        # Clear the cache for this event type so the new choice values are picked up
        cache.delete(f"schema_hash:{event_type.value}")

        # Get the new ETag
        new_etag = build_event_types_etag_header(empty_request)

        # The ETags should be different because a choice changed and cache was cleared
        assert (
            initial_etag != new_etag
        ), "ETag should change when a choice referenced in the schema is updated and cache is cleared"

    def test_build_event_type_etag_header_should_change_when_choice_changes(
        self, empty_request, five_event_types, five_choices
    ):
        """Test that the ETag for a single eventtype changes when a choice referenced in its schema is updated and cache is cleared."""

        # Create an eventtype with a schema that references choices
        event_type = five_event_types[0]
        schema_with_choices = {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Test Event Type",
                "type": "object",
                "properties": {
                    "habitat": {
                        "type": "string",
                        "title": "Habitat",
                        "enum": "{{enum___habitat___values}}",
                        "enumNames": "{{enum___habitat___names}}",
                    }
                },
            },
            "definition": ["habitat"],
        }
        event_type.schema = json.dumps(schema_with_choices)
        event_type.schema = event_type.schema.replace('"{{', "{{").replace('}}"', "}}")
        event_type.save(update_fields=["schema"])

        # Create choices for the habitat field
        choice1 = Choice.objects.create(
            model="activity.event", field="habitat", value="savanna", display="Savanna", ordernum=1
        )
        Choice.objects.create(model="activity.event", field="habitat", value="forest", display="Forest", ordernum=2)

        # Get the initial ETag
        initial_etag = build_event_type_etag_header(empty_request, eventtype_id=str(event_type.id))

        # Update one of the choices
        # Note: Don't use update_fields here because it bypasses auto_now fields
        choice1.display = "African Savanna"
        choice1.save()

        # Clear the cache for this event type so the new choice values are picked up
        cache.delete(f"schema_hash:{event_type.value}")

        # Get the new ETag
        new_etag = build_event_type_etag_header(empty_request, eventtype_id=str(event_type.id))

        # The ETags should be different because a choice changed and cache was cleared
        assert (
            initial_etag != new_etag
        ), "ETag should change when a choice referenced in the schema is updated and cache is cleared"

    def test_build_event_types_etag_header_caches_rendered_schemas(self, empty_request, five_event_types):
        """Test that rendered schemas are cached on the request during etag calculation."""

        # Create a real request-like object that can store attributes properly
        class MockRequest:
            def __init__(self, user, query_params):
                self.user = user
                self.GET = query_params
                self.headers = {}

        real_request = MockRequest(empty_request.user, empty_request.GET)

        # Build the etag - this should render and cache schemas
        etag = build_event_types_etag_header(real_request)

        # Verify etag was created
        assert etag is not None

        # Verify schemas were cached on the request
        assert hasattr(real_request, "_rendered_schema_cache")
        cache = real_request._rendered_schema_cache
        assert isinstance(cache, dict)
        assert len(cache) == len(five_event_types)

        # Verify each event type's schema is in the cache
        for event_type in five_event_types:
            assert event_type.value in cache
            cached_schema = cache[event_type.value]
            assert cached_schema is not None
            assert isinstance(cached_schema, dict)

    def test_serializer_uses_cached_schemas(self, empty_request, five_event_types):
        """Test that EventTypeSerializer uses cached schemas from etag calculation."""

        # First, build etag to populate cache
        build_event_types_etag_header(empty_request)
        assert hasattr(empty_request, "_rendered_schema_cache")

        # Track calls to get_schema_renderer_method during serialization
        render_call_count = {"count": 0}

        def count_renders(*args, **kwargs):
            render_call_count["count"] += 1

            return get_schema_renderer_method(*args, **kwargs)

        # Serialize event types - should use cached schemas
        with patch("activity.serializers.events.get_schema_renderer_method", side_effect=count_renders):
            for event_type in five_event_types:
                serializer = EventTypeSerializer(
                    event_type, context={"request": empty_request, "include_schema": False}
                )
                rep = serializer.to_representation(event_type)

                # Verify representation was created
                assert rep is not None

            # Verify that get_schema_renderer_method was NOT called during serialization
            # because cached schemas were used
            assert render_call_count["count"] == 0, "Schemas should be retrieved from cache, not re-rendered"

    def test_build_event_types_etag_header_uses_redis_cache(self, empty_request):
        """Test that schema hashes are cached in Redis across multiple requests."""

        # Create event types with DIFFERENT schemas to test caching properly
        event_types = []
        for i in range(3):
            schema = json.dumps(
                {
                    "schema": {
                        "properties": {f"field_{i}": {"type": "string", "title": f"Field {i}"}},
                        "$schema": "http://json-schema.org/draft-04/schema#",
                    },
                    "definition": [f"field_{i}"],
                }
            )
            event_types.append(EventTypeFactory.create(schema=schema, value=f"test_cache_{i}"))

        # Clear cache before test
        cache.clear()

        # Track actual rendering by monitoring cache.get and cache.set
        cache_get_count = {"count": 0, "hits": 0, "misses": 0}
        cache_set_count = {"count": 0}

        original_cache_get = cache.get
        original_cache_set = cache.set

        def tracked_cache_get(key, *args, **kwargs):
            if key.startswith("schema_hash:"):
                cache_get_count["count"] += 1
                result = original_cache_get(key, *args, **kwargs)
                if result is None:
                    cache_get_count["misses"] += 1
                else:
                    cache_get_count["hits"] += 1
                return result
            return original_cache_get(key, *args, **kwargs)

        def tracked_cache_set(key, value, *args, **kwargs):
            if key.startswith("schema_hash:"):
                cache_set_count["count"] += 1
            return original_cache_set(key, value, *args, **kwargs)

        # First call - should render schemas and cache them
        with patch.object(cache, "get", side_effect=tracked_cache_get):
            with patch.object(cache, "set", side_effect=tracked_cache_set):
                first_etag = build_event_types_etag_header(empty_request)
                first_cache_misses = cache_get_count["misses"]
                first_cache_sets = cache_set_count["count"]

                # Should have cache misses for each unique schema
                assert first_cache_misses >= len(
                    event_types
                ), f"First call should have at least {len(event_types)} cache misses, got {first_cache_misses}"
                assert first_cache_sets >= len(
                    event_types
                ), f"First call should set at least {len(event_types)} cache entries, got {first_cache_sets}"

        # Reset counters for second call with same request
        cache_get_count = {"count": 0, "hits": 0, "misses": 0}
        cache_set_count = {"count": 0}

        # Second call with same request - should use cached schema hashes
        with patch.object(cache, "get", side_effect=tracked_cache_get):
            with patch.object(cache, "set", side_effect=tracked_cache_set):
                second_etag = build_event_types_etag_header(empty_request)
                second_cache_hits = cache_get_count["hits"]
                second_cache_sets = cache_set_count["count"]

                # Should have cache hits (no new sets)
                assert second_cache_hits >= len(
                    event_types
                ), f"Second call should have at least {len(event_types)} cache hits, got {second_cache_hits}"
                assert second_cache_sets == 0, f"Second call should not set any cache entries, got {second_cache_sets}"

        # ETags should be identical when using the same request
        assert first_etag == second_etag, "ETags should be identical when using same request and schemas"

        # Clean up
        for et in event_types:
            et.delete()
        cache.clear()
