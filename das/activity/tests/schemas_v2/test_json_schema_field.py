import copy
import json
from pathlib import Path

import pytest

from rest_framework.serializers import ValidationError

from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.serializers.fields.json_schema import VALID_DRAFT, JSONSchemaField
from activity.tests.helpers.schema_test_utils import (
    minimal_json_schema,
    minimal_ui_schema,
)


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
        [
            "valid_nested_collection_schema",
            "valid_event_type_v2_schema",
            "valid_numeric_field_schema",
            "valid_choice_field_schema",
            "valid_multiple_choice_field_schema",
            "valid_boolean_field_schema",
            "valid_datetime_field_schema",
            "valid_date_field_schema",
            "valid_time_field_schema",
            "valid_text_field_schema",
            "valid_location_field_schema",
            "valid_rendered_choice_field_schema",
            "valid_rendered_multiple_choice_field_schema",
        ],
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

        assert f"$schema must be {VALID_DRAFT}" in str(e.value)

    @pytest.mark.parametrize("json_schema_fixture", ["invalid_schema_required_props_not_present"], indirect=True)
    def test_invalid_required_property_json(self, json_schema_fixture):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(json_schema_fixture)

        assert "Invalid JSON Schema: ['who_initiated_contact', 'ranger_casualties', 'opposition_casualties']" in str(
            e.value
        )

    @pytest.mark.parametrize(
        "input_schema,error_str",
        [
            (
                # Missing 'json' at root
                {"ui": minimal_ui_schema},
                "Invalid JSON Schema: 'json' is a required property at ",
            ),
            (
                # Missing $schema at json
                {"json": {}},
                "$schema must be https://json-schema.org/draft/2020-12/schema",
            ),
            (
                # Missing 'ui' at root
                {"json": minimal_json_schema},
                "Invalid JSON Schema: 'ui' is a required property at ",
            ),
            (
                # Missing 'properties' under 'json'
                {
                    "json": {"$schema": f"{VALID_DRAFT}"},
                    "ui": minimal_ui_schema,
                },
                "Invalid JSON Schema: 'properties' is a required property at json",
            ),
            (
                {
                    "json": minimal_json_schema,
                    "ui": {"headers": {}, "order": [], "sections": {}},
                },
                "Invalid JSON Schema: 'fields' is a required property at ui",
            ),
            (
                {
                    "json": minimal_json_schema,
                    "ui": {"fields": {}, "order": [], "sections": {}},
                },
                "Invalid JSON Schema: 'headers' is a required property at ui",
            ),
            (
                {
                    "json": minimal_json_schema,
                    "ui": {"fields": {}, "headers": {}, "sections": {}},
                },
                "Invalid JSON Schema: 'order' is a required property at ui",
            ),
            (
                {
                    "json": minimal_json_schema,
                    "ui": {"fields": {}, "headers": {}, "order": []},
                },
                "Invalid JSON Schema: 'sections' is a required property at ui",
            ),
        ],
    )
    def test_missing_root_properties(self, input_schema, error_str):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(input_schema)

        assert error_str in str(e.value)

    # --- Tests for Specific Field Schema Validations (Using Fixtures) --- #
    @pytest.mark.parametrize(
        "json_schema_fixture, error_str_part1, error_str_part2",
        [
            (
                "invalid_numeric_default_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testNum",
            ),
            (
                "invalid_numeric_type_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testNum",
            ),
            (
                "invalid_choice_default_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testChoice",
            ),
            # (
            #     "invalid_choice_url_format_schema",
            #     "is not valid under any of the given schemas",
            #     "at json.properties.testChoice",
            # ),
            (
                "invalid_boolean_default_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testBool",
            ),
            (
                "invalid_boolean_type_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testBool",
            ),
            (
                "invalid_datetime_default_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testDateTime",
            ),
            (
                "invalid_datetime_format_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testDateTime",
            ),
            (
                "invalid_datetime_type_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testDateTime",
            ),
            (
                "invalid_text_field_schema",
                "is not valid under any of the given schemas",
                "at json.properties.first_field",
            ),
            (
                "invalid_location_type_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testLocation",
            ),
            (
                "invalid_location_missing_properties_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testLocation",
            ),
        ],
        indirect=["json_schema_fixture"],
    )
    def test_invalid_field_json(self, json_schema_fixture, error_str_part1, error_str_part2):
        """Tests validation failures for various field definitions using fixture files."""
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(json_schema_fixture)

        error_message = str(e.value)
        assert error_str_part1 in error_message
        assert error_str_part2 in error_message

    # --- Helpers for Section Validation Tests --- #

    def _create_default_section(self, label):
        """Creates a minimally valid section structure."""
        return {"label": label, "columns": 1, "isActive": True, "leftColumn": [], "rightColumn": []}

    def _create_default_header(self, label, section):
        """Creates a minimally valid header structure."""
        return {"label": label, "section": section, "size": "MEDIUM"}

    def _get_base_schema_for_section_tests(self):
        """Helper to create a MINIMALLY valid base schema for section validation tests."""
        return {
            "json": copy.deepcopy(minimal_json_schema),
            "ui": copy.deepcopy(minimal_ui_schema),
        }

    # --- Tests for _validate_parent_references --- #

    def test_valid_section_references(self):
        """Tests that a schema with valid section references passes when validate_sections=True."""
        schema = self._get_base_schema_for_section_tests()
        # Populate UI elements for this test using helpers
        schema["ui"]["sections"] = {
            "section-a": self._create_default_section("Section A"),
            "section-b": self._create_default_section("Section B"),
        }
        schema["ui"]["headers"] = {"header-1": self._create_default_header("Header 1", "section-a")}
        schema["ui"]["order"] = ["section-a", "section-b"]

        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        # If this raises ValidationError, the test will fail automatically
        field_schema.to_internal_value(schema)

    def test_invalid_header_section_reference(self):
        """Tests that validation fails if a header references a non-existent section."""
        schema = self._get_base_schema_for_section_tests()
        # Populate UI elements for this test using helpers
        schema["ui"]["sections"] = {"section-a": self._create_default_section("Section A")}
        schema["ui"]["headers"] = {
            # Create header with invalid section reference
            "header-1": self._create_default_header("Header 1", "non_existent_section")
        }
        # schema["ui"]["order"] remains empty [] from base

        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(schema)
        expected_error = (
            "'header-1' has an invalid 'parent' or 'section': 'non_existent_section' does not exist in 'sections'."
        )
        assert "Validation errors:" in str(e.value)
        assert expected_error in str(e.value)

    def test_invalid_order_section_reference(self):
        """Tests that validation fails if an order item references a non-existent section."""
        schema = self._get_base_schema_for_section_tests()
        # Populate UI elements for this test using helpers
        schema["ui"]["sections"] = {"section-a": self._create_default_section("Section A")}
        # schema["ui"]["headers"] remains empty {} from base
        schema["ui"]["order"] = ["section-a", "non_existent_section"]

        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(schema)
        expected_error = "non_existent_section in 'order' does not exist in 'sections'"
        assert "Validation errors:" in str(e.value)
        assert expected_error in str(e.value)

    def test_multiple_invalid_section_references(self):
        """Tests that multiple section reference errors are reported together."""
        schema = self._get_base_schema_for_section_tests()
        # Populate UI elements for this test using helpers
        schema["ui"]["sections"] = {"section-a": self._create_default_section("Section A")}
        schema["ui"]["headers"] = {
            # Create header with invalid section reference
            "header-1": self._create_default_header("Header 1", "non_existent_section1")
        }
        schema["ui"]["order"] = ["section-a", "non_existent_section2"]

        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(schema)

        expected_error1 = (
            "'header-1' has an invalid 'parent' or 'section': 'non_existent_section1' does not exist in 'sections'."
        )
        expected_error2 = "non_existent_section2 in 'order' does not exist in 'sections'"
        error_str = str(e.value)
        assert "Validation errors:" in error_str
        assert expected_error1 in error_str
        assert expected_error2 in error_str

    def test_section_validation_disabled(self):
        """Tests that invalid section references pass when validate_sections=False."""
        schema = self._get_base_schema_for_section_tests()
        # Populate UI elements with errors that would fail if validate_sections=True, using helpers
        schema["ui"]["sections"] = {"section-a": self._create_default_section("Section A")}
        schema["ui"]["headers"] = {"header-1": self._create_default_header("Header 1", "non_existent_section1")}
        schema["ui"]["order"] = ["section-a", "non_existent_section2"]

        # Initialize with validate_sections=False (default)
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        try:
            # This should now pass both the main schema and the (disabled) section validation.
            field_schema.to_internal_value(schema)
        except ValidationError as e:
            # No validation error should occur at all when section validation is off
            # and the base schema is otherwise valid.
            pytest.fail(f"Validation failed unexpectedly even when section validation was disabled: {e}")


class TestMetaSchemaPropertyConstraints:
    """
    Tests for the meta-schema constraints on EventType V2 schemas.

    These tests verify the oneOf constraint requiring either additionalProperties
    or unevaluatedProperties, plus mandatory type and required properties.
    """

    def _build_schema(self, json_overrides=None):
        """Build a valid schema with optional overrides to the json section."""
        schema = {
            "json": copy.deepcopy(minimal_json_schema),
            "ui": copy.deepcopy(minimal_ui_schema),
        }
        if json_overrides:
            schema["json"].update(json_overrides)
        return schema

    def _remove_json_key(self, schema, key):
        """Remove a key from the json section of the schema."""
        if key in schema["json"]:
            del schema["json"][key]
        return schema

    # --- Valid Schemas (oneOf constraint) ---

    def test_valid_schema_with_unevaluated_properties(self):
        """Schema with unevaluatedProperties: false should be valid."""
        schema = self._build_schema()
        # Ensure only unevaluatedProperties is present
        self._remove_json_key(schema, "additionalProperties")
        schema["json"]["unevaluatedProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None

    def test_valid_schema_with_additional_properties(self):
        """Schema with additionalProperties: false should be valid."""
        schema = self._build_schema()
        # Ensure only additionalProperties is present
        self._remove_json_key(schema, "unevaluatedProperties")
        schema["json"]["additionalProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None

    # --- Invalid Schemas (oneOf constraint violations) ---

    def test_invalid_schema_with_both_properties(self):
        """Schema with BOTH additionalProperties AND unevaluatedProperties should fail oneOf."""
        schema = self._build_schema()
        schema["json"]["additionalProperties"] = False
        schema["json"]["unevaluatedProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        # oneOf fails when schema matches BOTH branches
        assert "is valid under each of" in error_message

    def test_invalid_schema_with_neither_property(self):
        """Schema with NEITHER additionalProperties NOR unevaluatedProperties should fail."""
        schema = self._build_schema()
        self._remove_json_key(schema, "additionalProperties")
        self._remove_json_key(schema, "unevaluatedProperties")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "is not valid under any of the given schemas" in error_message

    # --- Required properties tests ---

    def test_invalid_schema_missing_type(self):
        """Schema missing 'type: object' should fail."""
        schema = self._build_schema()
        self._remove_json_key(schema, "type")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "'type' is a required property" in error_message

    def test_invalid_schema_missing_required_array(self):
        """Schema missing 'required' array should fail."""
        schema = self._build_schema()
        self._remove_json_key(schema, "required")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "'required' is a required property" in error_message

    def test_invalid_schema_missing_properties(self):
        """Schema missing 'properties' object should fail."""
        schema = self._build_schema()
        self._remove_json_key(schema, "properties")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "'properties' is a required property" in error_message

    # --- Property value constraints ---

    def test_invalid_type_value(self):
        """Schema with type != 'object' should fail."""
        schema = self._build_schema({"type": "array"})

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "'object' was expected at json.type" in error_message

    def test_invalid_additional_properties_value(self):
        """Schema with additionalProperties: true should fail (must be false)."""
        schema = self._build_schema()
        self._remove_json_key(schema, "unevaluatedProperties")
        schema["json"]["additionalProperties"] = True

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "False was expected at json.additionalProperties" in error_message

    def test_invalid_unevaluated_properties_value(self):
        """Schema with unevaluatedProperties: true should fail (must be false)."""
        schema = self._build_schema()
        self._remove_json_key(schema, "additionalProperties")
        schema["json"]["unevaluatedProperties"] = True

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "False was expected at json.unevaluatedProperties" in error_message
