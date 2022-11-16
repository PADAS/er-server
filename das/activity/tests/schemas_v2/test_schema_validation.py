import copy

import pytest

from rest_framework.serializers import ValidationError

from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.serializers.fields.json_schema import VALID_DRAFT, JSONSchemaField
from activity.tests.helpers.schema_test_utils import (
    minimal_json_schema,
    minimal_ui_schema,
)


class TestJsonSchemaFieldBasics:
    """
    Tests for basic JSONSchemaField input validation and fixture-based schema tests.

    These tests verify the field handles various input types correctly and validates
    schemas loaded from fixture files.
    """

    @pytest.mark.parametrize(
        "json_schema_fixture",
        [
            "valid_nested_collection_schema",
            "valid_event_type_v2_schema",
            "valid_numeric_field_schema",
            "valid_choice_field_schema",
            "valid_multiple_choice_field_schema",
            "valid_boolean_field_schema",
            "valid_boolean_field_minimal_schema",
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


class TestRootSchemaValidation:
    """
    Tests for root-level schema structure and properties.

    These tests verify required root properties (json, ui) and their sub-properties,
    plus optional root properties like auto-generate, readonly, icon_id, and image_url.
    """

    def _build_schema(self, root_overrides=None):
        """Build a valid schema with optional root-level overrides."""
        schema = {
            "json": copy.deepcopy(minimal_json_schema),
            "ui": copy.deepcopy(minimal_ui_schema),
        }
        if root_overrides:
            schema.update(root_overrides)
        return schema

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

    @pytest.mark.parametrize(
        "property_name, valid_value",
        [
            ("auto-generate", True),
            ("auto-generate", False),
            ("readonly", True),
            ("readonly", False),
            ("icon_id", "some-icon-uuid-or-id"),
            ("icon_id", ""),
            ("image_url", "https://example.com/image.png"),
            ("image_url", ""),
        ],
    )
    def test_valid_new_root_properties(self, property_name, valid_value):
        """Test that new root properties accept valid values."""
        schema = self._build_schema({property_name: valid_value})
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        # Should not raise ValidationError
        assert field.to_internal_value(schema)

    @pytest.mark.parametrize(
        "property_name, invalid_value, expected_error",
        [
            ("auto-generate", "not-a-boolean", "is not of type 'boolean'"),
            ("auto-generate", 123, "is not of type 'boolean'"),
            ("readonly", "not-a-boolean", "is not of type 'boolean'"),
            ("readonly", 123, "is not of type 'boolean'"),
            ("icon_id", 123, "is not of type 'string'"),
            ("icon_id", True, "is not of type 'string'"),
            ("image_url", 123, "is not of type 'string'"),
            ("image_url", True, "is not of type 'string'"),
        ],
    )
    def test_invalid_new_root_properties_types(self, property_name, invalid_value, expected_error):
        """Test that new root properties reject invalid types."""
        schema = self._build_schema({property_name: invalid_value})
        field = JSONSchemaField(meta_schema=main_event_type_schema)

        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert expected_error in error_message
        assert property_name in error_message


class TestSectionReferenceValidation:
    """
    Tests for UI section reference validation.

    These tests verify the validate_sections parameter that checks headers
    and order items reference existing sections.
    """

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

    @pytest.mark.parametrize("json_schema_fixture", ["ui_schema_missing_parent_section"], indirect=True)
    def test_invalid_ui_schema_missing_parents(self, json_schema_fixture):
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(json_schema_fixture)

        err = str(e.value)
        assert "Validation errors:" in err
        assert "'header-1' has an invalid 'parent' or 'section': 'section-3' does not exist in 'sections'" in err
        assert "section-3 in 'order' does not exist in 'sections'" in err

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
            # Create header with invalid section reference (must match ^section-.* pattern)
            "header-1": self._create_default_header("Header 1", "section-nonexistent")
        }
        # schema["ui"]["order"] remains empty [] from base

        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(schema)
        expected_error = (
            "'header-1' has an invalid 'parent' or 'section': 'section-nonexistent' does not exist in 'sections'."
        )
        assert "Validation errors:" in str(e.value)
        assert expected_error in str(e.value)

    def test_invalid_order_section_reference(self):
        """Tests that validation fails if an order item references a non-existent section."""
        schema = self._get_base_schema_for_section_tests()
        # Populate UI elements for this test using helpers
        schema["ui"]["sections"] = {"section-a": self._create_default_section("Section A")}
        # schema["ui"]["headers"] remains empty {} from base
        schema["ui"]["order"] = ["section-a", "section-nonexistent"]

        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(schema)
        expected_error = "section-nonexistent in 'order' does not exist in 'sections'"
        assert "Validation errors:" in str(e.value)
        assert expected_error in str(e.value)

    def test_multiple_invalid_section_references(self):
        """Tests that multiple section reference errors are reported together."""
        schema = self._get_base_schema_for_section_tests()
        # Populate UI elements for this test using helpers
        schema["ui"]["sections"] = {"section-a": self._create_default_section("Section A")}
        schema["ui"]["headers"] = {
            # Create header with invalid section reference (must match ^section-.* pattern)
            "header-1": self._create_default_header("Header 1", "section-nonexistent1")
        }
        schema["ui"]["order"] = ["section-a", "section-nonexistent2"]

        field_schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
        with pytest.raises(ValidationError) as e:
            field_schema.to_internal_value(schema)

        expected_error1 = (
            "'header-1' has an invalid 'parent' or 'section': 'section-nonexistent1' does not exist in 'sections'."
        )
        expected_error2 = "section-nonexistent2 in 'order' does not exist in 'sections'"
        error_str = str(e.value)
        assert "Validation errors:" in error_str
        assert expected_error1 in error_str
        assert expected_error2 in error_str

    def test_section_validation_disabled(self):
        """Tests that invalid section references pass when validate_sections=False."""
        schema = self._get_base_schema_for_section_tests()
        # Populate UI elements with errors that would fail if validate_sections=True, using helpers
        schema["ui"]["sections"] = {"section-a": self._create_default_section("Section A")}
        schema["ui"]["headers"] = {"header-1": self._create_default_header("Header 1", "section-nonexistent1")}
        schema["ui"]["order"] = ["section-a", "section-nonexistent2"]

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


class TestCollectionFieldMetaSchemaConstraints:
    """
    Tests for the meta-schema constraints on collection fields.

    Collection fields have their own oneOf constraint at the items level,
    requiring either additionalProperties or unevaluatedProperties.
    """

    def _build_collection_schema(self, items_overrides=None):
        """Build a valid schema with a collection field."""
        schema = {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "test_collection": {
                        "type": "array",
                        "title": "Test Collection",
                        "items": {
                            "type": "object",
                            "properties": {
                                # Must match text_field_schema: requires deprecated, description, title, type
                                "name": {
                                    "type": "string",
                                    "title": "Name",
                                    "description": "",
                                    "deprecated": False,
                                },
                            },
                            "required": [],
                            "additionalProperties": False,
                        },
                        "unevaluatedItems": False,
                    }
                },
                "required": [],
                "unevaluatedProperties": False,
            },
            "ui": copy.deepcopy(minimal_ui_schema),
        }
        if items_overrides:
            schema["json"]["properties"]["test_collection"]["items"].update(items_overrides)
        return schema

    def _remove_items_key(self, schema, key):
        """Remove a key from the items section of the collection field."""
        items = schema["json"]["properties"]["test_collection"]["items"]
        if key in items:
            del items[key]
        return schema

    # --- Valid Collection Schemas (oneOf constraint) ---

    def test_valid_collection_with_additional_properties(self):
        """Collection items with additionalProperties: false should be valid."""
        schema = self._build_collection_schema()
        # Default already has additionalProperties

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None

    def test_valid_collection_with_unevaluated_properties(self):
        """Collection items with unevaluatedProperties: false should be valid."""
        schema = self._build_collection_schema()
        self._remove_items_key(schema, "additionalProperties")
        schema["json"]["properties"]["test_collection"]["items"]["unevaluatedProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None

    # --- Invalid Collection Schemas (oneOf constraint violations) ---

    def test_invalid_collection_with_both_properties(self):
        """Collection items with BOTH properties should fail oneOf."""
        schema = self._build_collection_schema()
        schema["json"]["properties"]["test_collection"]["items"]["additionalProperties"] = False
        schema["json"]["properties"]["test_collection"]["items"]["unevaluatedProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        # oneOf fails when schema matches BOTH branches - wrapped in anyOf error
        assert "is not valid under any of the given schemas" in error_message
        assert "test_collection" in error_message

    def test_invalid_collection_with_neither_property(self):
        """Collection items with NEITHER property should fail oneOf."""
        schema = self._build_collection_schema()
        self._remove_items_key(schema, "additionalProperties")
        self._remove_items_key(schema, "unevaluatedProperties")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "is not valid under any of the given schemas" in error_message

    # --- Required properties in collection items ---

    def test_invalid_collection_missing_type(self):
        """Collection items missing 'type' should fail."""
        schema = self._build_collection_schema()
        self._remove_items_key(schema, "type")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        # Validation error is wrapped in anyOf at the collection field level
        assert "is not valid under any of the given schemas" in error_message
        assert "test_collection" in error_message

    def test_invalid_collection_missing_required_array(self):
        """Collection items missing 'required' array should fail."""
        schema = self._build_collection_schema()
        self._remove_items_key(schema, "required")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        # Validation error is wrapped in anyOf at the collection field level
        assert "is not valid under any of the given schemas" in error_message
        assert "test_collection" in error_message

    def test_invalid_collection_missing_properties(self):
        """Collection items missing 'properties' should fail."""
        schema = self._build_collection_schema()
        self._remove_items_key(schema, "properties")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        # Validation error is wrapped in anyOf at the collection field level
        assert "is not valid under any of the given schemas" in error_message
        assert "test_collection" in error_message
