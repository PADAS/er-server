import json
from pathlib import Path

import pytest

from rest_framework.serializers import ValidationError

from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.serializers.fields.json_schema import JSONSchemaField


class TestJsonSchemaField:
    @pytest.fixture
    def json_schema_fixture(self, request):
        fixture_name = request.param

        fixture_path = Path(__file__).parent.parent / "fixtures" / f"{fixture_name}.json"
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.mark.parametrize("json_schema_fixture", ["ui_schema_missing_parent_section"], indirect=True)
    def test_invalid_ui_schema_missing_parents(self, json_schema_fixture):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(json_schema_fixture)

        err = str(e.value)
        assert "Validation errors:" in err
        assert "'header-1' has an invalid 'parent' or 'section': 'section-3' does not exist in 'sections'" in err
        assert "section-3 in 'order' does not exist in 'sections'" in err

    @pytest.mark.parametrize(
        "json_schema_fixture",
        ["valid_nested_collection_schema", "valid_event_type_v2_schema"],
        indirect=True,
    )
    def test_valid_event_type_schemas(self, json_schema_fixture):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)

        assert field_schema.to_internal_value(json_schema_fixture)

    def test_invalid_json_types(self):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value("invalid json schema")
        assert "Invalid JSON string" in str(e.value)

        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(b"invalid json schema")
        assert "Invalid JSON data" in str(e.value)

        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(["anything"])
        assert "The schema must be a JSON object." in str(e.value)

    @pytest.mark.parametrize("json_schema_fixture", ["invalid_draft_schema"], indirect=True)
    def test_invalid_draft_json_schema(self, json_schema_fixture):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(json_schema_fixture)

        assert (
            "[ErrorDetail(string=\"Invalid JSON Schema: 'https://json-schema.org/draft/2020-12/schema' was expected at json.$schema\", code='invalid')]"
            == str(e.value)
        )

    @pytest.mark.parametrize("json_schema_fixture", ["invalid_schema_required_props_not_present"], indirect=True)
    def test_invalid_required_property_json(self, json_schema_fixture):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(json_schema_fixture)

        assert "Invalid JSON Schema: ['who_initiated_contact', 'ranger_casualties', 'opposition_casualties']" in str(
            e.value
        )

    @pytest.mark.parametrize("json_schema_fixture", ["invalid_text_field_schema"], indirect=True)
    def test_invalid_text_field_json(self, json_schema_fixture):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(json_schema_fixture)

        assert "is not valid under any of the given schemas" in str(e.value)

    @pytest.mark.parametrize(
        "input_schema,error_str",
        [
            ({}, "Invalid JSON Schema: 'json' is a required property at "),
            ({"json": {}}, "Invalid JSON Schema: 'ui' is a required property at "),
            ({"json": {}, "ui": {}}, "Invalid JSON Schema: '$schema' is a required property at json"),
            ({"json": {"$schema": ""}, "ui": {}}, "Invalid JSON Schema: 'properties' is a required property at json"),
            (
                {"json": {"$schema": "", "properties": {}}, "ui": {}},
                "Invalid JSON Schema: 'fields' is a required property at ui",
            ),
            (
                {"json": {"$schema": "", "properties": {}}, "ui": {"fields": {}}},
                "Invalid JSON Schema: 'headers' is a required property at ui",
            ),
            (
                {"json": {"$schema": "", "properties": {}}, "ui": {"fields": {}, "headers": {}}},
                "Invalid JSON Schema: 'order' is a required property at ui",
            ),
            (
                {"json": {"$schema": "", "properties": {}}, "ui": {"fields": {}, "headers": {}, "order": []}},
                "Invalid JSON Schema: 'sections' is a required property at ui",
            ),
        ],
    )
    def test_missing_root_properties(self, input_schema, error_str):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(input_schema)

        assert error_str in str(e.value)
