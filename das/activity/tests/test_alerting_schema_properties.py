"""
Comprehensive unit tests for AlertingSchemaPropertiesAdapter.

Tests the AlertingSchemaPropertiesAdapter class with focus on:
1. V1 vs V2 schema processing equivalence
2. All supported field types for alert conditions
3. Choice field extraction and processing
4. Superuser request creation and handling

Now using shared schema builders and DRY helpers for clean, maintainable tests!
"""

import json

import pytest

from activity.alerting.schema_properties import AlertingSchemaPropertiesAdapter
from activity.models import EventType
from activity.tests.helpers.schema_test_utils import (
    V1SchemaBuilder,
    V2SchemaBuilder,
    simple_choices,
    standard_choices,
)
from factories import EventTypeFactory


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestAlertingSchemaPropertiesAdapter:
    """Comprehensive unit tests for AlertingSchemaPropertiesAdapter class."""

    def test_v1_string_field_processing(self, five_event_categories):
        """Test V1 string field processing."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create V1 EventType with string field using shared builder
        v1_schema = V1SchemaBuilder.simple_field("description", "string")
        v1_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_1,
            schema=json.dumps(v1_schema),
            value="test_v1_string",
            display="Test V1 String Field",
        )

        result = adapter.get_alert_properties(v1_event_type)

        assert result.status == "success"
        assert result.version == EventType.VersionChoices.VERSION_1
        assert "description" in result.properties
        assert result.properties["description"]["type"] == "string"
        assert result.properties["description"]["title"] == "Description"
        assert len(result.choice_options_map) == 0  # No choice fields

    def test_v2_string_field_processing(self, five_event_categories):
        """Test V2 string field processing."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create V2 EventType with string field using shared builder
        v2_schema = V2SchemaBuilder.simple_field("description", "string")
        v2_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(v2_schema),
            value="test_v2_string",
            display="Test V2 String Field",
        )

        result = adapter.get_alert_properties(v2_event_type)

        assert result.status == "success"
        assert result.version == EventType.VersionChoices.VERSION_2
        assert "description" in result.properties
        assert result.properties["description"]["type"] == "string"
        assert result.properties["description"]["title"] == "Description"
        assert len(result.choice_options_map) == 0  # No choice fields

    def test_v1_number_field_processing(self, five_event_categories):
        """Test V1 number field processing."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create V1 EventType with number field using shared builder
        v1_schema = V1SchemaBuilder.simple_field("count", "number", minimum=0)
        v1_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_1,
            schema=json.dumps(v1_schema),
            value="test_v1_number",
            display="Test V1 Number Field",
        )

        result = adapter.get_alert_properties(v1_event_type)

        assert result.status == "success"
        assert "count" in result.properties
        assert result.properties["count"]["type"] == "number"
        assert result.properties["count"]["title"] == "Count"
        assert result.properties["count"]["minimum"] == 0

    def test_v2_number_field_processing(self, five_event_categories):
        """Test V2 number field processing."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create V2 EventType with number field using shared builder
        v2_schema = V2SchemaBuilder.simple_field("count", "number", minimum=0)
        v2_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(v2_schema),
            value="test_v2_number",
            display="Test V2 Number Field",
        )

        result = adapter.get_alert_properties(v2_event_type)

        assert result.status == "success"
        assert "count" in result.properties
        assert result.properties["count"]["type"] == "number"
        assert result.properties["count"]["title"] == "Count"
        assert result.properties["count"]["minimum"] == 0

    def test_v1_choice_field_processing(self, five_event_categories):
        """Test V1 choice field processing with enumNames."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create V1 EventType with choice field using shared builder and predefined choices
        v1_schema = V1SchemaBuilder.choice_field("status", standard_choices)
        v1_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_1,
            schema=json.dumps(v1_schema),
            value="test_v1_choice",
            display="Test V1 Choice Field",
        )

        result = adapter.get_alert_properties(v1_event_type)

        assert result.status == "success"
        assert "status" in result.properties
        assert "enumNames" in result.properties["status"]

        # Test choice options extraction
        assert "status" in result.choice_options_map
        choice_options = result.choice_options_map["status"]
        assert choice_options["active"] == "Active"
        assert choice_options["inactive"] == "Inactive"
        assert choice_options["pending"] == "Pending"

    def test_v2_choice_field_processing(self, five_event_categories):
        """Test V2 choice field processing with oneOf structure."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create V2 EventType with choice field using shared builder and predefined choices
        v2_schema = V2SchemaBuilder.choice_field("status", standard_choices)
        v2_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(v2_schema),
            value="test_v2_choice",
            display="Test V2 Choice Field",
        )

        result = adapter.get_alert_properties(v2_event_type)

        assert result.status == "success"
        assert "status" in result.properties
        assert "anyOf" in result.properties["status"]

        # Test choice options extraction from V2 oneOf structure
        assert "status" in result.choice_options_map
        choice_options = result.choice_options_map["status"]
        assert choice_options["active"] == "Active"
        assert choice_options["inactive"] == "Inactive"
        assert choice_options["pending"] == "Pending"

    def test_equivalent_v1_v2_schemas_comparison(self, five_event_categories):
        """Test that equivalent V1 and V2 schemas produce comparable results."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create equivalent multi-field schemas using shared builders
        priority_choices = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}

        # Build equivalent V1 and V2 multi-field schemas
        v1_schema = V1SchemaBuilder.multi_field(
            {
                "description": {"type": "string"},
                "priority": {"type": "number", "minimum": 1, "maximum": 10},
                "category": {"type": "string", "enumNames": priority_choices},
            }
        )

        v2_schema = V2SchemaBuilder.multi_field(
            {
                "description": {"type": "string"},
                "priority": {"type": "number", "minimum": 1, "maximum": 10},
                "category": {"type": "string", "choices": priority_choices},
            }
        )

        category = five_event_categories[0]
        v1_event_type = EventTypeFactory.create(
            category=category,
            version=EventType.VersionChoices.VERSION_1,
            schema=json.dumps(v1_schema),
            value="comparison_v1",
            display="Test V1 Comparison Schema",
        )
        v2_event_type = EventTypeFactory.create(
            category=category,
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(v2_schema),
            value="comparison_v2",
            display="Test V2 Comparison Schema",
        )

        v1_result = adapter.get_alert_properties(v1_event_type)
        v2_result = adapter.get_alert_properties(v2_event_type)

        # Both should succeed
        assert v1_result.status == "success"
        assert v2_result.status == "success"

        # Should have same field names
        assert set(v1_result.properties.keys()) == set(v2_result.properties.keys())
        assert set(v1_result.properties.keys()) == {"description", "priority", "category"}

        # Compare field types
        for field_name in v1_result.properties.keys():
            v1_field = v1_result.properties[field_name]
            v2_field = v2_result.properties[field_name]
            assert v1_field["type"] == v2_field["type"]
            assert v1_field["title"] == v2_field["title"]

        # Compare choice options for category field
        assert "category" in v1_result.choice_options_map
        assert "category" in v2_result.choice_options_map

        v1_choices = v1_result.choice_options_map["category"]
        v2_choices = v2_result.choice_options_map["category"]

        # Should have equivalent choice options
        assert v1_choices == v2_choices
        assert set(v1_choices.keys()) == {"critical", "high", "medium", "low"}
        assert v1_choices["critical"] == "Critical"
        assert v2_choices["critical"] == "Critical"

    def test_mixed_field_types_processing(self, five_event_categories):
        """Test processing of schemas with mixed field types."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create V1 schema with mixed field types using shared builder
        v1_mixed_schema = V1SchemaBuilder.multi_field(
            {
                "text_field": {"type": "string"},
                "number_field": {"type": "number", "minimum": 0},
                "choice_field": {"type": "string", "enumNames": simple_choices},
            }
        )

        v1_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_1,
            schema=json.dumps(v1_mixed_schema),
            value="test_v1_mixed",
            display="Test V1 Mixed Field Types",
        )

        result = adapter.get_alert_properties(v1_event_type)

        assert result.status == "success"
        assert len(result.properties) == 3

        # Verify field types
        assert result.properties["text_field"]["type"] == "string"
        assert result.properties["number_field"]["type"] == "number"
        assert result.properties["choice_field"]["type"] == "string"
        assert "enumNames" in result.properties["choice_field"]

        # Verify choice options extraction
        assert len(result.choice_options_map) == 1
        assert "choice_field" in result.choice_options_map
        choice_options = result.choice_options_map["choice_field"]
        assert choice_options["option1"] == "Option 1"
        assert choice_options["option2"] == "Option 2"

    def test_v2_choice_list_field_processing(self, five_event_categories):
        """V2 multi-select (choice list) fields have choice options extracted."""
        adapter = AlertingSchemaPropertiesAdapter()

        multi_choices = {"bushmeat": "Bush Meat", "ivory": "Ivory", "timber": "Timber"}
        v2_schema = V2SchemaBuilder.choice_list_field("items_confiscated", multi_choices)
        v2_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(v2_schema),
            value="test_v2_multi_choice",
            display="Test V2 Multi-Select Choice",
        )

        result = adapter.get_alert_properties(v2_event_type)

        assert result.status == "success"
        assert "items_confiscated" in result.properties

        # Multi-select should have its choice options extracted
        assert "items_confiscated" in result.choice_options_map
        choice_options = result.choice_options_map["items_confiscated"]
        assert choice_options == multi_choices

    def test_v2_mixed_single_and_multi_select(self, five_event_categories):
        """Schema with both single-select and multi-select fields."""
        adapter = AlertingSchemaPropertiesAdapter()

        single_choices = {"low": "Low", "high": "High"}
        multi_choices = {"bushmeat": "Bush Meat", "ivory": "Ivory"}
        v2_schema = V2SchemaBuilder.choice_list_field("items", multi_choices)
        # Add a single-select field
        v2_schema["json"]["properties"]["severity"] = {
            "type": "string",
            "title": "Severity",
            "deprecated": False,
            "description": "",
            "anyOf": [{"oneOf": [{"const": k, "title": v} for k, v in single_choices.items()]}],
        }

        v2_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_2,
            schema=json.dumps(v2_schema),
            value="test_v2_mixed_select",
            display="Test V2 Mixed Select",
        )

        result = adapter.get_alert_properties(v2_event_type)

        assert result.status == "success"
        assert "items" in result.choice_options_map
        assert result.choice_options_map["items"] == multi_choices
        assert "severity" in result.choice_options_map
        assert result.choice_options_map["severity"] == single_choices

    def test_v1_schema_processing_error_handling(self, five_event_categories):
        """Test V1 schema processing error handling."""
        adapter = AlertingSchemaPropertiesAdapter()

        # Create V1 EventType with invalid schema using shared helper
        invalid_schema = {"invalid": "schema format"}
        v1_event_type = EventTypeFactory.create(
            category=five_event_categories[0],
            version=EventType.VersionChoices.VERSION_1,
            schema=json.dumps(invalid_schema),
            value="test_v1_invalid",
            display="Test V1 Invalid Schema",
        )

        result = adapter.get_alert_properties(v1_event_type)

        assert result.status == "failure"
        assert len(result.errors) > 0
        assert result.properties == {}
        assert result.choice_options_map == {}
