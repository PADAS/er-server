"""
Tests for V2 EventType schema validation with conditional logic.

Tests complete schema validation (UI + JSON together) for conditional sections.

Operator → Field Type Compatibility:
- CONTAINS: Text, Choice List, Multi-Select, Null value variant
- IS_EXACTLY: Text, Numeric, Choice List, Boolean, Multi-Select
- IS_EMPTY: All field types (incl. Boolean, Multi-Select)
- IS_NOT_EMPTY: All field types (Text, Numeric, Choice, DateTime, Location, Attachment, Collection, Boolean, Multi-Select)
- IS_CONTAINED_BY: Multi-Select
- IS_NOT_CONTAINED_BY: Multi-Select
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
            pytest.param("contains_multiselect_field", id="multiselect"),
            pytest.param("contains_null_value", id="null_value"),
        ],
    )
    def test_valid_contains_condition(self, schema_field, fixture_name):
        """Valid schema with CONTAINS condition on supported field types."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)


# =============================================================================
# IS_NOT_EMPTY Operator Tests
# =============================================================================


class TestIsNotEmptyCondition:
    """IS_NOT_EMPTY operator: show section when field has any meaningful value."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("is_not_empty_text_field", id="text"),
            pytest.param("is_not_empty_numeric_field", id="numeric"),
            pytest.param("is_not_empty_choice_field", id="choice"),
            pytest.param("is_not_empty_datetime_field", id="datetime"),
            pytest.param("is_not_empty_location_field", id="location"),
            pytest.param("is_not_empty_attachment_field", id="attachment"),
            pytest.param("is_not_empty_collection_field", id="collection"),
            pytest.param("is_not_empty_boolean_field", id="boolean"),
            pytest.param("is_not_empty_multiselect_field", id="multiselect"),
        ],
    )
    def test_valid_is_not_empty_condition(self, schema_field, fixture_name):
        """Valid schema with IS_NOT_EMPTY condition on all field types."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)


# =============================================================================
# IS_EMPTY Operator Tests
# =============================================================================


class TestIsEmptyCondition:
    """IS_EMPTY operator: show section when field is empty/null."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("is_empty_text_field", id="text"),
            pytest.param("is_empty_numeric_field", id="numeric"),
            pytest.param("is_empty_choice_field", id="choice"),
            pytest.param("is_empty_datetime_field", id="datetime"),
            pytest.param("is_empty_location_field", id="location"),
            pytest.param("is_empty_attachment_field", id="attachment"),
            pytest.param("is_empty_collection_field", id="collection"),
            pytest.param("is_empty_multiselect_field", id="multiselect"),
            pytest.param("is_empty_boolean_field", id="boolean"),
        ],
    )
    def test_valid_is_empty_condition(self, schema_field, fixture_name):
        """Valid schema with IS_EMPTY condition on all field types."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)


# =============================================================================
# IS_EXACTLY Operator Tests
# =============================================================================


class TestIsExactlyCondition:
    """IS_EXACTLY operator: show section when field equals specific value."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("is_exactly_text_field", id="text"),
            pytest.param("is_exactly_numeric_field", id="numeric"),
            pytest.param("is_exactly_choice_field", id="choice"),
            pytest.param("is_exactly_numeric_zero", id="numeric_zero"),
            pytest.param("is_exactly_multiselect_field", id="multiselect"),
            pytest.param("is_exactly_boolean_field", id="boolean"),
        ],
    )
    def test_valid_is_exactly_condition(self, schema_field, fixture_name):
        """Valid schema with IS_EXACTLY condition on supported field types."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)


# =============================================================================
# IS_CONTAINED_BY Operator Tests
# =============================================================================


class TestIsContainedByCondition:
    """IS_CONTAINED_BY operator: show section when multi-select values are within allowed set."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("is_contained_by_multiselect_field", id="multiselect"),
        ],
    )
    def test_valid_is_contained_by_condition(self, schema_field, fixture_name):
        """Valid schema with IS_CONTAINED_BY condition on multi-select field."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)


# =============================================================================
# IS_NOT_CONTAINED_BY Operator Tests
# =============================================================================


class TestIsNotContainedByCondition:
    """IS_NOT_CONTAINED_BY operator: show section when multi-select values are NOT within set."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            pytest.param("is_not_contained_by_multiselect_field", id="multiselect"),
        ],
    )
    def test_valid_is_not_contained_by_condition(self, schema_field, fixture_name):
        """Valid schema with IS_NOT_CONTAINED_BY condition on multi-select field."""
        schema = load_fixture(fixture_name)
        result = schema_field.to_internal_value(schema)
        assert result is not None
        assert isinstance(result, dict)
