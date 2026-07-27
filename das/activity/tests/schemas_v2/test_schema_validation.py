from __future__ import annotations

import copy
from typing import Any

import pytest
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema.validators import Draft202012Validator

from rest_framework.serializers import ValidationError

from activity.schemas.eventtype_meta_schemas import (
    FIELD_TITLE_MAX_LENGTH,
    main_event_type_schema,
)
from activity.serializers.fields.json_schema import VALID_DRAFT, JSONSchemaField
from activity.tests.helpers.schema_test_utils import (
    minimal_json_schema,
    minimal_ui_schema,
)


def _build_schema_with_ref(ref: str) -> dict:
    """Build a minimal but valid event-type schema whose choice field uses a single $ref."""
    return {
        "json": {
            **copy.deepcopy(minimal_json_schema),
            "properties": {
                "testChoice": {
                    "title": "Test Choice",
                    "type": "string",
                    "deprecated": False,
                    "anyOf": [{"$ref": ref}],
                },
            },
            "required": ["testChoice"],
        },
        "ui": copy.deepcopy(minimal_ui_schema),
    }


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
            "valid_text_field_format_uri_schema",
            "valid_text_field_format_uuid_schema",
            "valid_text_field_format_email_schema",
            "valid_text_field_pattern_schema",
            "valid_location_field_schema",
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
                "invalid_text_field_format_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testText",
            ),
            (
                "invalid_text_field_pattern_schema",
                "is not valid under any of the given schemas",
                "at json.properties.testText",
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


class TestFieldSchemaTitleMaxLength:
    """Tests for field schema title maxLength constraint (FIELD_TITLE_MAX_LENGTH)."""

    def test_field_title_max_length_constant(self):
        """FIELD_TITLE_MAX_LENGTH must be 1000."""
        assert FIELD_TITLE_MAX_LENGTH == 1000

    def test_valid_text_field_with_title_at_max_length(self):
        """A text field with title length equal to FIELD_TITLE_MAX_LENGTH is valid."""
        schema = {
            "json": {
                **copy.deepcopy(minimal_json_schema),
                "properties": {
                    "long_title_field": {
                        "type": "string",
                        "title": "x" * FIELD_TITLE_MAX_LENGTH,
                        "deprecated": False,
                    }
                },
                "required": ["long_title_field"],
            },
            "ui": copy.deepcopy(minimal_ui_schema),
        }
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field_schema.to_internal_value(schema)
        assert result is not None

    def test_invalid_text_field_with_title_over_max_length(self):
        """A text field with title length exceeding FIELD_TITLE_MAX_LENGTH is invalid."""
        schema = {
            "json": {
                **copy.deepcopy(minimal_json_schema),
                "properties": {
                    "too_long_title_field": {
                        "type": "string",
                        "title": "x" * (FIELD_TITLE_MAX_LENGTH + 1),
                        "deprecated": False,
                    }
                },
                "required": ["too_long_title_field"],
            },
            "ui": copy.deepcopy(minimal_ui_schema),
        }
        field_schema = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field_schema.to_internal_value(schema)
        error_message = str(exc_info.value)
        assert "is not valid under any of the given schemas" in error_message
        assert "too_long_title_field" in error_message


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


class TestAttachmentFieldJsonSchemaValidation:
    """Tests for the attachment field JSON schema validation using the array-of-objects shape.

    Background
    ----------
    The attachment field json subschema (``attachmentFieldJSONSchema``) now
    represents an attachment field as an **array of objects** — each object
    has a required ``uploadId`` property (a UUID string) that references an
    uploaded file:

        {
            "deprecated": <bool>,          # required
            "items": {                      # required — exact const shape
                "properties": {
                    "uploadId": {
                        "format": "uuid",   #   const
                        "type": "string"    #   const
                    }
                },
                "required": ["uploadId"],  #   const
                "type": "object",          #   const
                "unevaluatedProperties": false  # const
            },
            "maxItems": <int>,             # optional
            "minItems": <int>,             # optional
            "title": <str>,                # required, max 1000 chars
            "type": "array",               # required const
            "uniqueItems": true            # required const
        }

    The ``items`` shape is a const enforced by the meta-schema: any deviation
    from the exact ``uploadId``/uuid structure causes all ``anyOf`` branches to
    fail.

    Note: ``additionalProperties: False`` is set on the attachment subschema
    and on both other ``type: array`` subschemas (``multipleChoiceListField``
    and ``collectionField``), so extra properties cause the ``anyOf`` to fail
    for all branches.
    """

    _VALID_UI = {
        "fields": {
            "photo": {
                "allowableFileTypes": [],
                "type": "ATTACHMENT",
                "parent": "section-1",
            }
        },
        "headers": {},
        "order": ["section-1"],
        "sections": {
            "section-1": {
                "columns": 1,
                "isActive": True,
                "label": "",
                "leftColumn": [{"name": "photo", "type": "field"}],
                "rightColumn": [],
            }
        },
    }

    _VALID_ITEMS = {
        "properties": {"uploadId": {"format": "uuid", "type": "string"}},
        "required": ["uploadId"],
        "type": "object",
        "unevaluatedProperties": False,
    }

    def _build_schema(self, photo_field: dict[str, Any]) -> dict[str, Any]:
        """Build a minimal V2 schema with the given attachment field definition."""
        return {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"photo": photo_field},
                "required": [],
                "unevaluatedProperties": False,
            },
            "ui": self._VALID_UI,
        }

    def test_fully_specified_attachment_field_is_accepted(self) -> None:
        """A fully-specified attachment field with all optional keys is accepted."""
        schema = self._build_schema(
            {
                "deprecated": False,
                "description": "Upload a photo",
                "items": self._VALID_ITEMS,
                "maxItems": 5,
                "minItems": 1,
                "title": "Photos",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None

    def test_minimal_attachment_field_with_only_required_keys_is_accepted(self) -> None:
        """A minimal attachment field with only the required keys is accepted.

        ``description``, ``minItems``, and ``maxItems`` are optional and may be omitted.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": self._VALID_ITEMS,
                "title": "Photo",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None

    def test_attachment_field_with_uniqueItems_false_is_rejected(self) -> None:
        """An attachment field with ``uniqueItems: false`` is rejected.

        ``attachmentFieldJSONSchema`` requires ``uniqueItems: {const: true}``, so
        ``false`` fails the const check there.  ``multipleChoiceListFieldJSONSchema``
        rejects first at the ``items`` level: its ``items`` sub-schema requires
        ``{anyOf, type: 'string'}`` with ``additionalProperties: False``, and the
        test input's items object ``{properties, required, type: 'object',
        unevaluatedProperties}`` matches none of those keys.
        ``collectionFieldJSONSchema`` fails at the outer field level: ``uniqueItems``
        is not in its ``properties`` map (``additionalProperties: False`` rejects it)
        and ``unevaluatedItems`` is required but absent.  All ``anyOf`` branches fail.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": self._VALID_ITEMS,
                "title": "Photo",
                "type": "array",
                "uniqueItems": False,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)
        assert "is not valid under any of the given schemas" in str(exc_info.value)

    def test_attachment_field_with_wrong_items_format_is_rejected(self) -> None:
        """An attachment field whose ``items.properties.uploadId`` carries ``format: "uri"`` is rejected.

        ``attachmentFieldJSONSchema.items.properties.uploadId`` requires
        ``{"const": "uuid"}`` for ``format``, so ``"uri"`` fails the const check.
        ``multipleChoiceListFieldJSONSchema`` rejects at the ``items`` level: its
        ``items`` sub-schema requires ``{anyOf, type: 'string'}`` with
        ``additionalProperties: False``, and the test input's items object
        ``{properties, required, type: 'object', unevaluatedProperties}`` matches
        none of those keys.  ``collectionFieldJSONSchema`` fails at the outer field
        level: ``uniqueItems`` is not in its ``properties`` map
        (``additionalProperties: False`` rejects it) and ``unevaluatedItems`` is
        required but absent.  All ``anyOf`` branches fail.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": {
                    "properties": {"uploadId": {"format": "uri", "type": "string"}},
                    "required": ["uploadId"],
                    "type": "object",
                    "unevaluatedProperties": False,
                },
                "title": "Photo",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)
        assert "is not valid under any of the given schemas" in str(exc_info.value)

    def test_attachment_field_with_items_missing_format_is_rejected(self) -> None:
        """An attachment field whose ``items.properties.uploadId`` omits ``format`` is rejected.

        ``attachmentFieldJSONSchema.items.properties.uploadId`` requires both ``format``
        (const ``"uuid"``) and ``type`` (const ``"string"``).  Without ``format``, validation
        fails the ``required`` check inside the ``uploadId`` schema.  The other ``anyOf``
        branches also reject this shape (see ``test_attachment_field_with_wrong_items_format_is_rejected``
        for the cross-branch analysis).  All ``anyOf`` branches fail.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": {
                    "properties": {"uploadId": {"type": "string"}},
                    "required": ["uploadId"],
                    "type": "object",
                    "unevaluatedProperties": False,
                },
                "title": "Photo",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)
        assert "is not valid under any of the given schemas" in str(exc_info.value)

    def test_attachment_field_missing_required_key_items_is_rejected(self) -> None:
        """An attachment field that omits the required ``items`` key is rejected.

        ``attachmentFieldJSONSchema`` requires ``items``.  ``multipleChoiceListField``
        also requires ``items``.  ``collectionFieldJSONSchema`` also requires ``items``.
        A ``type: array`` object without ``items`` satisfies none of the array
        subschemas.  All ``anyOf`` branches fail.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "title": "Photo",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)
        assert "is not valid under any of the given schemas" in str(exc_info.value)

    def test_attachment_field_missing_required_key_uniqueItems_is_rejected(self) -> None:
        """An attachment field that omits the required ``uniqueItems`` key is rejected.

        ``attachmentFieldJSONSchema`` requires ``uniqueItems`` in its ``required``
        list.  Omitting the key (as opposed to setting it to ``false``) triggers the
        required-property check independently of the const check.
        ``multipleChoiceListFieldJSONSchema`` also requires ``uniqueItems`` and
        additionally rejects the items shape.  ``collectionFieldJSONSchema`` rejects
        at the outer field level: ``unevaluatedItems`` is required but absent.  All
        ``anyOf`` branches fail.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": self._VALID_ITEMS,
                "title": "Photo",
                "type": "array",
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)
        assert "is not valid under any of the given schemas" in str(exc_info.value)

    def test_attachment_field_with_additional_property_is_rejected(self) -> None:
        """An attachment field with an unsupported additional property is rejected.

        ``attachmentFieldJSONSchema`` has ``additionalProperties: False``, so
        ``maxLength`` (not in the allowed property list) is rejected there.
        ``multipleChoiceListFieldJSONSchema`` and ``collectionFieldJSONSchema`` also
        have ``additionalProperties: False`` and do not permit ``maxLength``.
        All ``anyOf`` branches that accept ``type: array`` fail.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": self._VALID_ITEMS,
                "maxLength": 100,
                "title": "Photo",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)
        assert "is not valid under any of the given schemas" in str(exc_info.value)

    def test_attachment_field_with_negative_min_items_is_rejected(self) -> None:
        """An attachment field with ``minItems: -1`` is rejected.

        ``attachmentFieldJSONSchema`` constrains ``minItems`` to ``minimum: 0``,
        so a negative value is invalid there.  All other ``anyOf`` branches that
        accept ``type: array`` also reject this shape.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": self._VALID_ITEMS,
                "minItems": -1,
                "title": "Photo",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)
        assert "is not valid under any of the given schemas" in str(exc_info.value)

    def test_attachment_field_with_negative_max_items_is_rejected(self) -> None:
        """An attachment field with ``maxItems: -1`` is rejected.

        ``attachmentFieldJSONSchema`` constrains ``maxItems`` to ``minimum: 0``,
        so a negative value is invalid there.  All other ``anyOf`` branches that
        accept ``type: array`` also reject this shape.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": self._VALID_ITEMS,
                "maxItems": -1,
                "title": "Photo",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)
        assert "is not valid under any of the given schemas" in str(exc_info.value)

    def test_attachment_field_with_zero_min_items_and_max_items_is_accepted(self) -> None:
        """An attachment field with ``minItems: 0`` and ``maxItems: 0`` is accepted.

        Zero is the lower bound for both constraints, so it must be a valid value.
        """
        schema = self._build_schema(
            {
                "deprecated": False,
                "items": self._VALID_ITEMS,
                "maxItems": 0,
                "minItems": 0,
                "title": "Photo",
                "type": "array",
                "uniqueItems": True,
            }
        )
        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None


class TestMetaSchemaPropertyConstraints:
    """
    Tests for the meta-schema constraints on EventType V2 schemas.

    The meta-schema requires unevaluatedProperties: false and does not accept
    additionalProperties as a valid property. It also enforces mandatory type,
    required, and properties keys.
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

    # --- Valid Schemas ---

    def test_valid_schema_with_unevaluated_properties(self):
        """Schema with unevaluatedProperties: false should be valid."""
        schema = self._build_schema()

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None

    # --- Legacy schemas (normalized by activity.schemas.normalization, then accepted) ---

    def test_schema_with_additional_properties_instead_is_normalized_and_accepted(self):
        """Legacy documents using additionalProperties are normalized to unevaluatedProperties before validation.

        See activity/schemas/normalization.py (Event-Type-Schema-Migration-Tool PR #11 shape).
        """
        schema = self._build_schema()
        self._remove_json_key(schema, "unevaluatedProperties")
        schema["json"]["additionalProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)

        assert "additionalProperties" not in result["json"]
        assert result["json"]["unevaluatedProperties"] is False

    def test_schema_with_additional_properties_alongside_unevaluated_properties_is_normalized_and_accepted(self):
        """Legacy documents carrying both keys are normalized by dropping additionalProperties."""
        schema = self._build_schema()
        schema["json"]["additionalProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)

        assert "additionalProperties" not in result["json"]
        assert result["json"]["unevaluatedProperties"] is False

    def test_metaschema_itself_still_rejects_additional_properties_without_normalization(self):
        """The leniency lives only in the normalization layer -- the metaschema is unchanged.

        Validating directly against the metaschema (bypassing JSONSchemaField, and therefore
        bypassing normalization) must still reject additionalProperties.
        """
        schema = self._build_schema()
        self._remove_json_key(schema, "unevaluatedProperties")
        schema["json"]["additionalProperties"] = False

        with pytest.raises(JsonSchemaValidationError):
            Draft202012Validator(main_event_type_schema).validate(schema)

    def test_invalid_schema_missing_unevaluated_properties(self):
        """Schema missing unevaluatedProperties should fail with required property error."""
        schema = self._build_schema()
        self._remove_json_key(schema, "unevaluatedProperties")

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "'unevaluatedProperties' is a required property" in error_message

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

    def test_invalid_unevaluated_properties_value(self):
        """Schema with unevaluatedProperties: true should fail (must be false)."""
        schema = self._build_schema()
        schema["json"]["unevaluatedProperties"] = True

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "False was expected at json.unevaluatedProperties" in error_message


class TestCollectionFieldMetaSchemaConstraints:
    """
    Tests for the meta-schema constraints on collection fields.

    Collection items require unevaluatedProperties: false and do not accept
    additionalProperties. The collection field itself requires deprecated,
    items, title, type, and unevaluatedItems.
    """

    def _build_collection_schema(self, items_overrides=None):
        """Build a valid schema with a collection field."""
        schema = {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "test_collection": {
                        "deprecated": False,
                        "type": "array",
                        "title": "Test Collection",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "title": "Name",
                                    "description": "",
                                    "deprecated": False,
                                },
                            },
                            "required": [],
                            "unevaluatedProperties": False,
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

    # --- Valid Collection Schemas ---

    def test_valid_collection_with_unevaluated_properties(self):
        """Collection items with unevaluatedProperties: false should be valid."""
        schema = self._build_collection_schema()

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None

    # --- Legacy collection schemas (normalized by activity.schemas.normalization, then accepted) ---

    def test_collection_items_with_additional_properties_instead_is_normalized_and_accepted(self):
        """Collection items using additionalProperties are normalized to unevaluatedProperties."""
        schema = self._build_collection_schema()
        self._remove_items_key(schema, "unevaluatedProperties")
        schema["json"]["properties"]["test_collection"]["items"]["additionalProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)

        items = result["json"]["properties"]["test_collection"]["items"]
        assert "additionalProperties" not in items
        assert items["unevaluatedProperties"] is False

    def test_collection_items_with_additional_properties_alongside_unevaluated_properties_is_normalized(self):
        """Collection items carrying both keys are normalized by dropping additionalProperties."""
        schema = self._build_collection_schema()
        schema["json"]["properties"]["test_collection"]["items"]["additionalProperties"] = False

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)

        items = result["json"]["properties"]["test_collection"]["items"]
        assert "additionalProperties" not in items
        assert items["unevaluatedProperties"] is False

    def test_metaschema_itself_still_rejects_collection_items_additional_properties(self):
        """The leniency lives only in the normalization layer -- the metaschema is unchanged."""
        schema = self._build_collection_schema()
        self._remove_items_key(schema, "unevaluatedProperties")
        schema["json"]["properties"]["test_collection"]["items"]["additionalProperties"] = False

        with pytest.raises(JsonSchemaValidationError):
            Draft202012Validator(main_event_type_schema).validate(schema)

    def test_invalid_collection_items_missing_unevaluated_properties(self):
        """Collection items missing unevaluatedProperties should fail."""
        schema = self._build_collection_schema()
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
        assert "is not valid under any of the given schemas" in error_message
        assert "test_collection" in error_message

    # --- minItems / maxItems lower-bound constraint ---

    def test_collection_field_with_negative_min_items_is_rejected(self):
        """A collection field with ``minItems: -1`` is rejected.

        ``collectionFieldJSONSchema`` constrains ``minItems`` to ``minimum: 0``,
        so a negative value must fail all ``anyOf`` branches.
        """
        schema = self._build_collection_schema()
        schema["json"]["properties"]["test_collection"]["minItems"] = -1

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "is not valid under any of the given schemas" in error_message
        assert "test_collection" in error_message

    def test_collection_field_with_negative_max_items_is_rejected(self):
        """A collection field with ``maxItems: -1`` is rejected.

        ``collectionFieldJSONSchema`` constrains ``maxItems`` to ``minimum: 0``,
        so a negative value must fail all ``anyOf`` branches.
        """
        schema = self._build_collection_schema()
        schema["json"]["properties"]["test_collection"]["maxItems"] = -1

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        with pytest.raises(ValidationError) as exc_info:
            field.to_internal_value(schema)

        error_message = str(exc_info.value)
        assert "is not valid under any of the given schemas" in error_message
        assert "test_collection" in error_message

    def test_collection_field_with_zero_min_items_and_max_items_is_accepted(self):
        """A collection field with ``minItems: 0`` and ``maxItems: 0`` is accepted.

        Zero is the lower bound for both constraints, so it must be a valid value.
        """
        schema = self._build_collection_schema()
        schema["json"]["properties"]["test_collection"]["minItems"] = 0
        schema["json"]["properties"]["test_collection"]["maxItems"] = 0

        field = JSONSchemaField(meta_schema=main_event_type_schema)
        result = field.to_internal_value(schema)
        assert result is not None


class TestAdditionalKeyWildcardInRefAllowlist:
    """
    Tests that the $ref allowlist for sources.json and subjects.json accepts any
    additional.<key> query parameter, not just the previously hard-coded keys.

    The `additional` column is an open JSONB bag; JSONFieldFilterSetMixin filters
    any additional.<key> via exact text match, so the metaschema must allow
    arbitrary additional.* keys while keeping non-additional params enumerated.
    """

    def _field(self) -> JSONSchemaField:
        return JSONSchemaField(meta_schema=main_event_type_schema)

    def test_subjects_ref_with_arbitrary_additional_key_is_valid(self):
        """A subjects.json $ref with additional.horn_length (not in old whitelist) validates."""
        schema = _build_schema_with_ref("/api/v2.0/schemas/subjects.json?additional.horn_length=30")
        result = self._field().to_internal_value(schema)
        assert result is not None

    def test_sources_ref_with_arbitrary_additional_key_is_valid(self):
        """A sources.json $ref with additional.whatever (not in old whitelist) validates."""
        schema = _build_schema_with_ref("/api/v2.0/schemas/sources.json?additional.whatever=x")
        result = self._field().to_internal_value(schema)
        assert result is not None

    def test_subjects_ref_with_double_underscore_key_is_rejected(self):
        """A subjects.json $ref using double underscore (additional__sex) is still rejected."""
        schema = _build_schema_with_ref("/api/v2.0/schemas/subjects.json?additional__sex=female")
        with pytest.raises(ValidationError) as exc_info:
            self._field().to_internal_value(schema)
        error_message = str(exc_info.value)
        assert "is not valid under any of the given schemas" in error_message
        assert "testChoice" in error_message
