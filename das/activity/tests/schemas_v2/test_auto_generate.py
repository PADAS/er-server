"""
Tests for V2 schema auto-generation from event data.
"""

import json

import pytest

from activity.models import EventType
from activity.schemas.auto_generate import V2SchemaAutoBuilder
from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.serializers.fields.json_schema import JSONSchemaField


class TestV2SchemaAutoBuilder:
    """Tests for the V2SchemaAutoBuilder class."""

    def test_generated_schema_validates_against_meta_schema(self):
        """Generated schema should validate against main_event_type_schema."""
        doc = {
            "species": "Elephant",
            "count": 10,
            "is_active": True,
            "observed_at": "2024-06-15T10:00:00Z",
            "report_url": "https://example.com/report",
            "location": {"latitude": -2.5, "longitude": 37.2},
        }
        schema = V2SchemaAutoBuilder.from_document(doc)

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        validated = field.to_internal_value(schema)

        assert validated == schema

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

    def test_boolean_values_are_inferred_as_boolean(self):
        """Boolean values should be inferred as BOOLEAN fields."""
        schema = V2SchemaAutoBuilder.from_document({"is_active": True, "name": "Test"})

        assert schema["json"]["properties"]["is_active"]["type"] == "boolean"
        assert schema["ui"]["fields"]["is_active"]["type"] == "BOOLEAN"
        assert "name" in schema["json"]["properties"]

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

    def test_url_inferred_as_text_with_uri_format(self):
        """URL strings should be inferred as TEXT fields with uri format."""
        schema = V2SchemaAutoBuilder.from_document(
            {
                "website": "https://example.com/page",
                "api_endpoint": "http://api.example.com/v1",
            }
        )

        assert schema["json"]["properties"]["website"]["type"] == "string"
        assert schema["json"]["properties"]["website"]["format"] == "uri"
        assert schema["json"]["properties"]["api_endpoint"]["type"] == "string"
        assert schema["json"]["properties"]["api_endpoint"]["format"] == "uri"
        assert schema["ui"]["fields"]["website"]["type"] == "TEXT"
        assert schema["ui"]["fields"]["api_endpoint"]["type"] == "TEXT"

    @pytest.mark.parametrize(
        "field_name,value,expected_format",
        [
            ("email", "user@example.com", "email"),
            ("external_id", "550e8400-e29b-41d4-a716-446655440000", "uuid"),
        ],
    )
    def test_string_format_inferred_as_text(self, field_name, value, expected_format):
        """Recognized string formats should be inferred as TEXT fields with matching format."""
        schema = V2SchemaAutoBuilder.from_document({field_name: value})
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        validated = field.to_internal_value(schema)

        assert schema["json"]["properties"][field_name]["type"] == "string"
        assert schema["json"]["properties"][field_name]["format"] == expected_format
        assert schema["ui"]["fields"][field_name]["type"] == "TEXT"
        assert validated == schema

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
                "field3": "another string",
            }
        )

        for field_name, ui_field in schema["ui"]["fields"].items():
            assert ui_field["parent"] == "section-1", f"Field {field_name} missing parent"


class TestComplexDocuments:
    """Tests for auto-generating schemas from complex/realistic documents."""

    def test_realistic_wildlife_event(self):
        """Test schema generation from a realistic wildlife event."""
        doc = {
            "species_name": "African Elephant",
            "animal_count": 12,
            "sighting_location": {"latitude": -2.5, "longitude": 37.2},
            "observed_at": "2024-06-15T08:30:00Z",
            "photo_url": "https://cdn.example.com/photos/elephant.jpg",
            "notes": "Herd moving towards water source",
        }

        schema = V2SchemaAutoBuilder.from_document(doc)

        assert schema["json"]["properties"]["species_name"]["type"] == "string"
        assert schema["json"]["properties"]["animal_count"]["type"] == "number"
        assert schema["json"]["properties"]["sighting_location"]["type"] == "object"
        assert schema["json"]["properties"]["observed_at"]["format"] == "date-time"
        assert schema["json"]["properties"]["photo_url"]["format"] == "uri"
        assert schema["json"]["properties"]["notes"]["type"] == "string"

        assert schema["ui"]["fields"]["species_name"]["type"] == "TEXT"
        assert schema["ui"]["fields"]["animal_count"]["type"] == "NUMERIC"
        assert schema["ui"]["fields"]["sighting_location"]["type"] == "LOCATION"
        assert schema["ui"]["fields"]["observed_at"]["type"] == "DATE_TIME"
        assert schema["ui"]["fields"]["photo_url"]["type"] == "TEXT"
        assert schema["ui"]["fields"]["notes"]["type"] == "TEXT"

    def test_patrol_report_event(self):
        """Test schema generation from a patrol report event."""
        doc = {
            "patrol_date": "2024-03-20",
            "patrol_start_time": "06:00:00",
            "kilometers_covered": 45.7,
            "incidents_reported": 3,
            "notes": "All clear",
        }

        schema = V2SchemaAutoBuilder.from_document(doc)

        assert schema["json"]["properties"]["patrol_date"]["format"] == "date"
        assert schema["json"]["properties"]["patrol_start_time"]["format"] == "time"
        assert schema["json"]["properties"]["kilometers_covered"]["type"] == "number"
        assert schema["json"]["properties"]["incidents_reported"]["type"] == "number"
        assert schema["json"]["properties"]["notes"]["type"] == "string"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSerializerIntegration:
    """Integration tests for auto-generate with the EventDetailsSerializer."""

    def test_v2_placeholder_triggers_auto_generate(self, cat1_cat2_categories, auto_generate_v2_marker_schema):
        """Test v2 placeholder schema triggers auto-generation.

        This tests the flow where v2 event types are created with a v2
        placeholder schema. When event data is posted, the system should:
        1. Detect the auto-generate marker
        2. Generate a v2 schema from the event data
        """
        from activity.serializers.event_details import EventDetailsSerializer

        cat1, _ = cat1_cat2_categories
        event_type = EventType.objects.create(
            value="test_auto_gen_v2",
            display="Test Auto Gen V2",
            category=cat1,
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(auto_generate_v2_marker_schema),
        )

        event_data = {
            "species": "Lion",
            "count": 5,
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

    def test_v1_placeholder_triggers_auto_generate_and_upgrades_to_v2(
        self, cat1_cat2_categories, auto_generate_v1_marker_schema
    ):
        """Test v1 placeholder schema triggers auto-generation and upgrades to v2.

        This tests the Django admin flow where v1 event types are created with
        a v1 placeholder schema. When event data is posted, the system should:
        1. Detect the auto-generate marker
        2. Generate a v2 schema from the event data
        3. Upgrade the event type from v1 to v2
        """
        from activity.serializers.event_details import EventDetailsSerializer

        cat1, _ = cat1_cat2_categories
        event_type = EventType.objects.create(
            value="test_v1_placeholder",
            display="Test V1 Placeholder",
            category=cat1,
            version=EventType.VersionChoices.VERSION_1,
            schema=json.dumps(auto_generate_v1_marker_schema),
        )

        assert event_type.version == EventType.VersionChoices.VERSION_1

        event_data = {
            "animal_name": "Elephant",
            "count": 10,
            "observed_at": "2024-06-15T10:00:00Z",
        }

        serializer = EventDetailsSerializer()
        result = serializer._handle_auto_generate(event_type, event_data)

        assert result is True

        event_type.refresh_from_db()

        # Should be upgraded to v2
        assert event_type.version == EventType.VersionChoices.VERSION_2

        # Schema should be v2 format with generated fields
        generated_schema = json.loads(event_type.schema)
        assert "auto-generate" not in generated_schema
        assert "json" in generated_schema
        assert "ui" in generated_schema
        assert generated_schema["json"]["$schema"] == "https://json-schema.org/draft/2020-12/schema"

        # Verify fields were generated from event data
        props = generated_schema["json"]["properties"]
        assert "animal_name" in props
        assert "count" in props
        assert "observed_at" in props


class TestAutoGeneratedSchemaMetaValidation:
    """Verify every field type produced by V2SchemaAutoBuilder validates against the meta-schema."""

    @pytest.mark.parametrize(
        "doc,expected_ui_type",
        [
            pytest.param({"plain_text": "hello"}, "TEXT", id="text_plain"),
            pytest.param({"url_field": "https://example.com"}, "TEXT", id="text_uri"),
            pytest.param({"email_field": "user@example.com"}, "TEXT", id="text_email"),
            pytest.param({"uuid_field": "550e8400-e29b-41d4-a716-446655440000"}, "TEXT", id="text_uuid"),
            pytest.param({"int_field": 42}, "NUMERIC", id="numeric_int"),
            pytest.param({"float_field": 3.14}, "NUMERIC", id="numeric_float"),
            pytest.param({"bool_field": True}, "BOOLEAN", id="boolean_true"),
            pytest.param({"bool_field": False}, "BOOLEAN", id="boolean_false"),
            pytest.param({"dt_field": "2024-01-15T10:30:00Z"}, "DATE_TIME", id="datetime"),
            pytest.param({"dt_field": "2024-01-15T10:30:00+02:00"}, "DATE_TIME", id="datetime_offset"),
            pytest.param({"date_field": "2024-01-15"}, "DATE_TIME", id="date"),
            pytest.param({"time_field": "14:30:00"}, "DATE_TIME", id="time"),
            pytest.param(
                {"loc_field": {"latitude": -1.29, "longitude": 36.82}},
                "LOCATION",
                id="location",
            ),
        ],
    )
    def test_single_field_validates_against_meta_schema(self, doc, expected_ui_type):
        """Each individual field type should produce a schema that passes meta-schema validation."""
        schema = V2SchemaAutoBuilder.from_document(doc)

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        validated = field.to_internal_value(schema)

        assert validated == schema

        field_name = next(iter(doc))
        assert schema["ui"]["fields"][field_name]["type"] == expected_ui_type

    def test_all_field_types_combined_validates_against_meta_schema(self):
        """A schema with every supported field type should pass meta-schema validation."""
        doc = {
            "description": "Herd near river",
            "animal_count": 12,
            "is_endangered": True,
            "observed_at": "2024-06-15T08:30:00Z",
            "patrol_date": "2024-06-15",
            "start_time": "06:00:00",
            "report_url": "https://cdn.example.com/report",
            "email_contact": "ranger@example.com",
            "external_id": "550e8400-e29b-41d4-a716-446655440000",
            "sighting_location": {"latitude": -2.5, "longitude": 37.2},
        }
        schema = V2SchemaAutoBuilder.from_document(doc)

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        validated = field.to_internal_value(schema)

        assert validated == schema
        assert len(schema["json"]["properties"]) == len(doc)

    def test_empty_document_validates_against_meta_schema(self):
        """An empty document should still produce a valid schema."""
        schema = V2SchemaAutoBuilder.from_document({})

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        validated = field.to_internal_value(schema)

        assert validated == schema

    def test_skipped_fields_still_produce_valid_schema(self):
        """Documents with unsupported types should produce a valid schema from remaining fields."""
        doc = {
            "name": "Test",
            "tags": ["one", "two"],
            "metadata": {"key": "value"},
            "count": 5,
        }
        schema = V2SchemaAutoBuilder.from_document(doc)

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        validated = field.to_internal_value(schema)

        assert validated == schema
        assert "tags" not in schema["json"]["properties"]
        assert "metadata" not in schema["json"]["properties"]
        assert "name" in schema["json"]["properties"]
        assert "count" in schema["json"]["properties"]
