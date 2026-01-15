"""
Tests for V2 EventType schema validation with conditional logic.

Tests complete schema validation (UI + JSON together) for conditional sections.

Operator → Field Type Compatibility:
- CONTAINS: Text, Choice List
- HAS_INPUT: All field types (Text, Numeric, Choice, DateTime, Location, Attachment, Collection)
- DOES_NOT_HAVE_INPUT: All field types
- INPUT_IS_EXACTLY: Text, Numeric, Choice List
"""

import json
from pathlib import Path

import pytest

from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.serializers.fields.json_schema import JSONSchemaField

# =============================================================================
# Fixtures
# =============================================================================

CONDITIONAL_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "conditional_schemas"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture by name."""
    fixture_path = CONDITIONAL_FIXTURES_DIR / f"{name}.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def schema_field():
    """JSONSchemaField instance for validation."""
    return JSONSchemaField(meta_schema=main_event_type_schema)


# =============================================================================
# CONTAINS Operator Tests
# =============================================================================


class TestContainsCondition:
    """CONTAINS operator: show section when field value contains a substring."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("contains_text_field", id="text"),
            pytest.param("contains_choice_field", id="choice"),
        ],
    )
    def test_valid_contains_condition(self, schema_field, fixture_name):
        """Valid schema with CONTAINS condition on supported field types."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)


# =============================================================================
# HAS_INPUT Operator Tests
# =============================================================================


class TestHasInputCondition:
    """HAS_INPUT operator: show section when field has any meaningful value."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("has_input_text_field", id="text"),
            pytest.param("has_input_numeric_field", id="numeric"),
            pytest.param("has_input_choice_field", id="choice"),
            pytest.param("has_input_datetime_field", id="datetime"),
            pytest.param("has_input_location_field", id="location"),
            pytest.param("has_input_attachment_field", id="attachment"),
            pytest.param("has_input_collection_field", id="collection"),
        ],
    )
    def test_valid_has_input_condition(self, schema_field, fixture_name):
        """Valid schema with HAS_INPUT condition on all field types."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)


# =============================================================================
# DOES_NOT_HAVE_INPUT Operator Tests
# =============================================================================


class TestDoesNotHaveInputCondition:
    """DOES_NOT_HAVE_INPUT operator: show section when field is empty/null."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("does_not_have_input_text_field", id="text"),
            pytest.param("does_not_have_input_numeric_field", id="numeric"),
            pytest.param("does_not_have_input_choice_field", id="choice"),
            pytest.param("does_not_have_input_datetime_field", id="datetime"),
            pytest.param("does_not_have_input_location_field", id="location"),
            pytest.param("does_not_have_input_attachment_field", id="attachment"),
            pytest.param("does_not_have_input_collection_field", id="collection"),
        ],
    )
    def test_valid_does_not_have_input_condition(self, schema_field, fixture_name):
        """Valid schema with DOES_NOT_HAVE_INPUT condition on all field types."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)


# =============================================================================
# INPUT_IS_EXACTLY Operator Tests
# =============================================================================


class TestInputIsExactlyCondition:
    """INPUT_IS_EXACTLY operator: show section when field equals specific value."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("input_is_exactly_text_field", id="text"),
            pytest.param("input_is_exactly_numeric_field", id="numeric"),
            pytest.param("input_is_exactly_choice_field", id="choice"),
            pytest.param("input_is_exactly_numeric_zero", id="numeric_zero"),
        ],
    )
    def test_valid_input_is_exactly_condition(self, schema_field, fixture_name):
        """Valid schema with INPUT_IS_EXACTLY condition on supported field types."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)
