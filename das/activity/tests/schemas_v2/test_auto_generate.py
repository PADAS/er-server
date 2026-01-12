"""
Tests for V2 schema auto-generation from event data.
"""

import json

import pytest

from activity.models import EventType
from activity.schemas.auto_generate import (
    V2SchemaAutoBuilder,
    generate_v2_schema_from_document,
    get_auto_generate_v2_marker_schema,
    should_auto_generate_v2,
)


class TestV2SchemaAutoBuilder:
    """Tests for the V2SchemaAutoBuilder class."""

    def test_empty_document_generates_empty_schema(self):
        """An empty document should generate an empty but valid V2 schema."""
        schema = V2SchemaAutoBuilder.from_document({})

        assert "json" in schema
        assert "ui" in schema
        assert schema["json"]["properties"] == {}
        assert schema["ui"]["fields"] == {}

    def test_string_field_inferred_as_text(self):
        """Plain strings should be inferred as TEXT fields."""
        schema = V2SchemaAutoBuilder.from_document({"description": "A test description"})

        json_field = schema["json"]["properties"]["description"]
        ui_field = schema["ui"]["fields"]["description"]

        assert json_field["type"] == "string"
        assert json_field["title"] == "Description"
        assert json_field["deprecated"] is False
        assert ui_field["type"] == "TEXT"
        assert ui_field["inputType"] == "SHORT_TEXT"

    def test_number_field_inferred_as_numeric(self):
        """Integer and float values should be inferred as NUMERIC fields."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "count": 42,
                "temperature": 36.5,
            }
        )

        assert schema["json"]["properties"]["count"]["type"] == "number"
        assert schema["json"]["properties"]["temperature"]["type"] == "number"
        assert schema["ui"]["fields"]["count"]["type"] == "NUMERIC"
        assert schema["ui"]["fields"]["temperature"]["type"] == "NUMERIC"

    def test_boolean_field_inferred_as_boolean(self):
        """Boolean values should be inferred as BOOLEAN fields."""
        schema = V2SchemaAutoBuilder.from_document({"is_active": True})

        json_field = schema["json"]["properties"]["is_active"]
        ui_field = schema["ui"]["fields"]["is_active"]

        assert json_field["type"] == "boolean"
        assert json_field["title"] == "Is Active"
        assert ui_field["type"] == "BOOLEAN"

    def test_iso_datetime_inferred_as_datetime(self):
        """ISO datetime strings should be inferred as DATE_TIME fields."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "created_at": "2024-01-15T10:30:00Z",
            }
        )

        json_field = schema["json"]["properties"]["created_at"]
        ui_field = schema["ui"]["fields"]["created_at"]

        assert json_field["type"] == "string"
        assert json_field["format"] == "date-time"
        assert ui_field["type"] == "DATE_TIME"

    def test_iso_datetime_with_offset_inferred_as_datetime(self):
        """ISO datetime with timezone offset should be inferred as DATE_TIME."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "event_time": "2024-01-15T10:30:00+02:00",
            }
        )

        json_field = schema["json"]["properties"]["event_time"]
        assert json_field["format"] == "date-time"

    def test_iso_date_inferred_as_date(self):
        """ISO date strings should be inferred as DATE_TIME with date format."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "birth_date": "1990-05-20",
            }
        )

        json_field = schema["json"]["properties"]["birth_date"]
        ui_field = schema["ui"]["fields"]["birth_date"]

        assert json_field["type"] == "string"
        assert json_field["format"] == "date"
        assert ui_field["type"] == "DATE_TIME"

    def test_iso_time_inferred_as_time(self):
        """ISO time strings should be inferred as DATE_TIME with time format."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "start_time": "14:30:00",
            }
        )

        json_field = schema["json"]["properties"]["start_time"]
        assert json_field["format"] == "time"

    def test_url_inferred_as_link(self):
        """URL strings should be inferred as LINK fields."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "website": "https://example.com/page",
                "api_endpoint": "http://api.example.com/v1",
            }
        )

        assert schema["json"]["properties"]["website"]["format"] == "uri"
        assert schema["json"]["properties"]["api_endpoint"]["format"] == "uri"
        assert schema["ui"]["fields"]["website"]["type"] == "LINK"
        assert schema["ui"]["fields"]["api_endpoint"]["type"] == "LINK"

    def test_location_object_inferred_as_location(self):
        """Dict with latitude/longitude should be inferred as LOCATION field."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "position": {"latitude": -1.2921, "longitude": 36.8219},
            }
        )

        json_field = schema["json"]["properties"]["position"]
        ui_field = schema["ui"]["fields"]["position"]

        assert json_field["type"] == "object"
        assert "latitude" in json_field["properties"]
        assert "longitude" in json_field["properties"]
        assert json_field["properties"]["latitude"]["minimum"] == -90
        assert json_field["properties"]["latitude"]["maximum"] == 90
        assert json_field["properties"]["longitude"]["minimum"] == -180
        assert json_field["properties"]["longitude"]["maximum"] == 180
        assert ui_field["type"] == "LOCATION"

    def test_list_values_are_skipped(self):
        """List values should be skipped (not auto-generated)."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "tags": ["one", "two", "three"],
                "name": "test",
            }
        )

        assert "tags" not in schema["json"]["properties"]
        assert "name" in schema["json"]["properties"]

    def test_nested_dict_without_location_skipped(self):
        """Nested dicts that aren't locations should be skipped."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "metadata": {"key": "value"},
                "name": "test",
            }
        )

        assert "metadata" not in schema["json"]["properties"]
        assert "name" in schema["json"]["properties"]

    def test_title_generation_from_key(self):
        """Field keys should be converted to proper titles."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "animal_species_count": 5,
                "singleword": "test",
            }
        )

        assert schema["json"]["properties"]["animal_species_count"]["title"] == "Animal Species Count"
        assert schema["json"]["properties"]["singleword"]["title"] == "Singleword"

    def test_field_order_preserved(self):
        """Fields should appear in the UI in the same order they were in the doc."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "first": "a",
                "second": "b",
                "third": "c",
            }
        )

        left_column = schema["ui"]["sections"]["section-1"]["leftColumn"]
        field_names = [item["name"] for item in left_column]

        assert field_names == ["first", "second", "third"]

    def test_json_schema_structure_valid(self):
        """Generated JSON schema should have required v2 structure."""
        schema = V2SchemaAutoBuilder.from_document({"test": "value"})

        json_schema = schema["json"]
        assert json_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert json_schema["type"] == "object"
        assert json_schema["unevaluatedProperties"] is False
        assert "required" in json_schema
        assert "properties" in json_schema

    def test_ui_schema_structure_valid(self):
        """Generated UI schema should have required v2 structure."""
        schema = V2SchemaAutoBuilder.from_document({"test": "value"})

        ui_schema = schema["ui"]
        assert "fields" in ui_schema
        assert "headers" in ui_schema
        assert "order" in ui_schema
        assert "sections" in ui_schema
        assert ui_schema["order"] == ["section-1"]

    def test_all_fields_have_parent_section(self):
        """All UI fields should reference the parent section."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "field1": "a",
                "field2": 123,
                "field3": True,
            }
        )

        for field_name, ui_field in schema["ui"]["fields"].items():
            assert ui_field["parent"] == "section-1", f"Field {field_name} missing parent"


class TestGenerateV2SchemaFromDocument:
    """Tests for the generate_v2_schema_from_document function."""

    def test_convenience_function_works(self):
        """The convenience function should work like the builder."""
        doc = {"name": "Test", "count": 5}
        schema = generate_v2_schema_from_document(doc)

        assert "json" in schema
        assert "ui" in schema
        assert "name" in schema["json"]["properties"]
        assert "count" in schema["json"]["properties"]


class TestShouldAutoGenerateV2:
    """Tests for the should_auto_generate_v2 function."""

    def test_returns_true_for_marker_schema(self):
        """Should return True when auto-generate marker is present."""
        schema = {"auto-generate": True, "json": {}, "ui": {}}
        assert should_auto_generate_v2(schema) is True

    def test_returns_false_for_normal_schema(self):
        """Should return False for schemas without the marker."""
        schema = {"json": {}, "ui": {}}
        assert should_auto_generate_v2(schema) is False

    def test_returns_false_for_non_dict(self):
        """Should return False for non-dict inputs."""
        assert should_auto_generate_v2(None) is False
        assert should_auto_generate_v2("string") is False
        assert should_auto_generate_v2([]) is False

    def test_returns_false_for_explicit_false_marker(self):
        """Should return False when auto-generate is explicitly False."""
        schema = {"auto-generate": False, "json": {}, "ui": {}}
        assert should_auto_generate_v2(schema) is False


class TestGetAutoGenerateV2MarkerSchema:
    """Tests for the get_auto_generate_v2_marker_schema function."""

    def test_marker_schema_has_auto_generate_flag(self):
        """Marker schema should have the auto-generate flag set to True."""
        schema = get_auto_generate_v2_marker_schema()
        assert schema["auto-generate"] is True

    def test_marker_schema_is_valid_v2_structure(self):
        """Marker schema should be a valid V2 schema structure."""
        schema = get_auto_generate_v2_marker_schema()

        assert "json" in schema
        assert "ui" in schema
        assert schema["json"]["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "properties" in schema["json"]
        assert "fields" in schema["ui"]
        assert "sections" in schema["ui"]

    def test_marker_schema_has_placeholder_field(self):
        """Marker schema should have a placeholder field."""
        schema = get_auto_generate_v2_marker_schema()

        assert "placeholder" in schema["json"]["properties"]
        assert "placeholder" in schema["ui"]["fields"]


class TestComplexDocuments:
    """Tests for auto-generating schemas from complex/realistic documents."""

    def test_realistic_wildlife_event(self):
        """Test schema generation from a realistic wildlife event."""
        doc = {
            "species_name": "African Elephant",
            "animal_count": 12,
            "is_injured": False,
            "sighting_location": {"latitude": -2.5, "longitude": 37.2},
            "observed_at": "2024-06-15T08:30:00Z",
            "photo_url": "https://cdn.example.com/photos/elephant.jpg",
            "notes": "Herd moving towards water source",
        }

        schema = generate_v2_schema_from_document(doc)

        assert schema["json"]["properties"]["species_name"]["type"] == "string"
        assert schema["json"]["properties"]["animal_count"]["type"] == "number"
        assert schema["json"]["properties"]["is_injured"]["type"] == "boolean"
        assert schema["json"]["properties"]["sighting_location"]["type"] == "object"
        assert schema["json"]["properties"]["observed_at"]["format"] == "date-time"
        assert schema["json"]["properties"]["photo_url"]["format"] == "uri"
        assert schema["json"]["properties"]["notes"]["type"] == "string"

        assert schema["ui"]["fields"]["species_name"]["type"] == "TEXT"
        assert schema["ui"]["fields"]["animal_count"]["type"] == "NUMERIC"
        assert schema["ui"]["fields"]["is_injured"]["type"] == "BOOLEAN"
        assert schema["ui"]["fields"]["sighting_location"]["type"] == "LOCATION"
        assert schema["ui"]["fields"]["observed_at"]["type"] == "DATE_TIME"
        assert schema["ui"]["fields"]["photo_url"]["type"] == "LINK"
        assert schema["ui"]["fields"]["notes"]["type"] == "TEXT"

    def test_patrol_report_event(self):
        """Test schema generation from a patrol report event."""
        doc = {
            "patrol_date": "2024-03-20",
            "patrol_start_time": "06:00:00",
            "kilometers_covered": 45.7,
            "incidents_reported": 3,
            "all_clear": True,
        }

        schema = generate_v2_schema_from_document(doc)

        assert schema["json"]["properties"]["patrol_date"]["format"] == "date"
        assert schema["json"]["properties"]["patrol_start_time"]["format"] == "time"
        assert schema["json"]["properties"]["kilometers_covered"]["type"] == "number"
        assert schema["json"]["properties"]["incidents_reported"]["type"] == "number"
        assert schema["json"]["properties"]["all_clear"]["type"] == "boolean"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSerializerIntegration:
    """Integration tests for auto-generate with the EventDetailsSerializer."""

    def test_v2_auto_generate_updates_event_type_schema(self, cat1_cat2_categories):
        """Test that posting event data triggers V2 schema auto-generation."""
        from activity.serializers.event_details import EventDetailsSerializer

        cat1, _ = cat1_cat2_categories
        marker_schema = get_auto_generate_v2_marker_schema()
        event_type = EventType.objects.create(
            value="test_auto_gen_v2",
            display="Test Auto Gen V2",
            category=cat1,
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(marker_schema),
        )

        event_data = {
            "species": "Lion",
            "count": 5,
            "is_healthy": True,
            "observed_at": "2024-06-15T10:00:00Z",
        }

        serializer = EventDetailsSerializer()
        result = serializer._handle_auto_generate(event_type, event_data)

        assert result is True  # Auto-generation was triggered

        event_type.refresh_from_db()
        generated_schema = json.loads(event_type.schema)

        assert "auto-generate" not in generated_schema
        assert "json" in generated_schema
        assert "ui" in generated_schema

        props = generated_schema["json"]["properties"]
        assert props["species"]["type"] == "string"
        assert props["count"]["type"] == "number"
        assert props["is_healthy"]["type"] == "boolean"
        assert props["observed_at"]["format"] == "date-time"

    def test_v2_auto_generate_does_not_trigger_without_marker(self, cat1_cat2_categories):
        """Test that schemas without auto-generate marker are not modified."""
        from activity.serializers.event_details import EventDetailsSerializer

        cat1, _ = cat1_cat2_categories
        original_schema = {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "properties": {"existing_field": {"type": "string", "title": "Existing"}},
                "required": [],
                "type": "object",
                "unevaluatedProperties": False,
            },
            "ui": {
                "fields": {"existing_field": {"type": "TEXT", "parent": "section-1"}},
                "headers": {},
                "order": ["section-1"],
                "sections": {
                    "section-1": {"columns": 1, "isActive": True, "label": "", "leftColumn": [], "rightColumn": []}
                },
            },
        }

        event_type = EventType.objects.create(
            value="test_no_auto_gen_v2",
            display="Test No Auto Gen V2",
            category=cat1,
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(original_schema),
        )

        event_data = {"new_field": "new value"}

        serializer = EventDetailsSerializer()
        result = serializer._handle_auto_generate(event_type, event_data)

        assert result is False  # Auto-generation was NOT triggered

        event_type.refresh_from_db()
        schema_after = json.loads(event_type.schema)

        assert schema_after == original_schema
        assert "new_field" not in schema_after["json"]["properties"]

    def test_v1_auto_generate_upgrades_to_v2(self, cat1_cat2_categories):
        """Test that v1 event types with auto-generate marker are upgraded to v2."""
        from activity.serializers.event_details import EventDetailsSerializer

        cat1, _ = cat1_cat2_categories
        # V1-style auto-generate marker schema
        v1_marker_schema = {
            "auto-generate": True,
            "description": "Placeholder",
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Placeholder",
                "type": "object",
                "properties": {"placeholder": {"type": "string"}},
            },
            "definition": ["placeholder"],
        }

        event_type = EventType.objects.create(
            value="test_v1_auto_gen",
            display="Test V1 Auto Gen",
            category=cat1,
            version=EventType.VersionChoices.VERSION_1,
            schema=json.dumps(v1_marker_schema),
        )

        assert event_type.version == EventType.VersionChoices.VERSION_1

        event_data = {
            "animal_name": "Elephant",
            "count": 10,
        }

        serializer = EventDetailsSerializer()
        result = serializer._handle_auto_generate(event_type, event_data)

        assert result is True

        event_type.refresh_from_db()

        # Should be upgraded to v2
        assert event_type.version == EventType.VersionChoices.VERSION_2

        # Schema should be v2 format
        generated_schema = json.loads(event_type.schema)
        assert "auto-generate" not in generated_schema
        assert "json" in generated_schema
        assert "ui" in generated_schema
        assert generated_schema["json"]["$schema"] == "https://json-schema.org/draft/2020-12/schema"
