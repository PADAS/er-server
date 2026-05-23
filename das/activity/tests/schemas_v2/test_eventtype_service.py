"""Tests for EventTypeSchemaService."""

from __future__ import annotations

import json

import pytest

from activity.schemas.eventtype_service import EventTypeSchemaService
from activity.tests.helpers.schema_test_utils import V2SchemaBuilder


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestRemoveStrictValidationProperties:
    """Tests for the temporary removal of strict validation properties from V2 schemas."""

    def test_v2_schema_unevaluated_properties_removed_at_root(self):
        """V2 schema with unevaluatedProperties: false at root has it removed."""
        service = EventTypeSchemaService()
        schema = V2SchemaBuilder.multi_field(
            {
                "field1": {"type": "string", "title": "Field 1"},
            }
        )
        schema["json"]["unevaluatedProperties"] = False

        service._remove_strict_validation_properties(schema)

        assert "unevaluatedProperties" not in schema["json"]

    def test_v2_schema_additional_properties_removed_at_root(self):
        """V2 schema with additionalProperties: false at root has it removed."""
        service = EventTypeSchemaService()
        schema = V2SchemaBuilder.multi_field(
            {
                "field1": {"type": "string", "title": "Field 1"},
            }
        )
        # V2SchemaBuilder already adds additionalProperties: False by default

        service._remove_strict_validation_properties(schema)

        assert "additionalProperties" not in schema["json"]

    def test_v2_schema_both_properties_removed(self):
        """V2 schema with both properties at root has both removed."""
        service = EventTypeSchemaService()
        schema = V2SchemaBuilder.multi_field(
            {
                "field1": {"type": "string", "title": "Field 1"},
            }
        )
        schema["json"]["unevaluatedProperties"] = False
        schema["json"]["additionalProperties"] = False

        service._remove_strict_validation_properties(schema)

        assert "unevaluatedProperties" not in schema["json"]
        assert "additionalProperties" not in schema["json"]

    def test_nested_unevaluated_properties_preserved(self):
        """unevaluatedProperties in nested collection items is NOT removed."""
        service = EventTypeSchemaService()
        schema = V2SchemaBuilder.multi_field(
            {
                "items": {
                    "type": "array",
                    "title": "Items",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "title": "Name"},
                        },
                        "unevaluatedProperties": False,
                    },
                    "unevaluatedItems": False,
                },
            }
        )

        service._remove_strict_validation_properties(schema)

        # Root should not have these (they weren't there)
        assert "unevaluatedProperties" not in schema["json"]
        # Nested should still have it
        assert schema["json"]["properties"]["items"]["items"]["unevaluatedProperties"] is False
        assert schema["json"]["properties"]["items"]["unevaluatedItems"] is False

    def test_nested_location_unevaluated_properties_preserved(self):
        """unevaluatedProperties in nested location field is NOT removed."""
        service = EventTypeSchemaService()
        schema = V2SchemaBuilder.multi_field(
            {
                "location": {
                    "type": "object",
                    "title": "Location",
                    "properties": {
                        "latitude": {"type": "number"},
                        "longitude": {"type": "number"},
                    },
                    "required": ["latitude", "longitude"],
                    "unevaluatedProperties": False,
                },
            }
        )

        service._remove_strict_validation_properties(schema)

        # Root should not have it
        assert "unevaluatedProperties" not in schema["json"]
        # Nested location should still have it
        assert schema["json"]["properties"]["location"]["unevaluatedProperties"] is False

    def test_ui_section_preserved(self):
        """The UI section of the schema is preserved during mutation."""
        service = EventTypeSchemaService()
        schema = V2SchemaBuilder.multi_field(
            {
                "field1": {"type": "string", "title": "Field 1"},
            }
        )
        schema["json"]["unevaluatedProperties"] = False
        expected_ui_fields = {"field1"}

        service._remove_strict_validation_properties(schema)

        assert "ui" in schema
        assert set(schema["ui"]["fields"].keys()) == expected_ui_fields


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestGetRenderedSchemaPostprocessing:
    """Tests that postprocessing is applied correctly in get_rendered_schema."""

    def test_v2_event_type_gets_postprocessed(self, cat1_fire_v2_event_type):
        """V2 EventType schema has validation properties removed in rendered output."""
        from rest_framework.test import APIRequestFactory

        service = EventTypeSchemaService()
        request = APIRequestFactory().get("/")
        request.user = None  # Not used for this test

        # Add unevaluatedProperties to the stored schema
        schema = json.loads(cat1_fire_v2_event_type.schema)
        schema["json"]["unevaluatedProperties"] = False
        cat1_fire_v2_event_type.schema = json.dumps(schema)
        cat1_fire_v2_event_type.save()

        result = service.get_rendered_schema(cat1_fire_v2_event_type, request)

        assert result.status == "success"
        assert "unevaluatedProperties" not in result.schema["json"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestGetRawSchemaNotPostprocessed:
    """Tests that raw schemas are NOT postprocessed."""

    def test_raw_schema_unchanged(self, cat1_fire_v2_event_type):
        """Raw schema output is NOT postprocessed - properties remain."""
        service = EventTypeSchemaService()

        # Add properties to the stored schema
        schema = json.loads(cat1_fire_v2_event_type.schema)
        schema["json"]["unevaluatedProperties"] = False
        schema["json"]["additionalProperties"] = False
        cat1_fire_v2_event_type.schema = json.dumps(schema)
        cat1_fire_v2_event_type.save()

        result = service.get_raw_schema(cat1_fire_v2_event_type)

        assert result.status == "success"
        # Raw schema should keep the properties
        assert result.schema["json"]["unevaluatedProperties"] is False
        assert result.schema["json"]["additionalProperties"] is False
