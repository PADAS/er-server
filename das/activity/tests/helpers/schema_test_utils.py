"""
Shared utilities for V1/V2 EventType schema testing.
"""

import json
from typing import Optional

from django.urls import reverse

from activity.alerting.businessrules import (
    EventActions,
    _generate_aggregate_event_variables_class,
    export_rule_data,
)

# =============================================================================
# Constants
# =============================================================================

# JSON Schema draft versions
V1_DRAFT = "http://json-schema.org/draft-07/schema#"
V2_DRAFT = "https://json-schema.org/draft/2020-12/schema"
VALID_DRAFT = V2_DRAFT  # Alias for backward compatibility

# Test choice data constants
standard_choices = {"active": "Active", "inactive": "Inactive", "pending": "Pending"}
simple_choices = {"option1": "Option 1", "option2": "Option 2"}

# Minimal valid V2 schema structures
minimal_json_schema = {
    "$schema": V2_DRAFT,
    "type": "object",
    "properties": {},
    "required": [],
    "unevaluatedProperties": False,
}

minimal_ui_schema = {
    "sections": {},
    "headers": {},
    "fields": {},
    "order": [],
}

minimal_event_type_schema = {
    "json": minimal_json_schema,
    "ui": minimal_ui_schema,
}


# =============================================================================
# Schema Builders
# =============================================================================


class V1SchemaBuilder:
    """Builder for V1 EventType JSON schemas using DRY patterns."""

    @staticmethod
    def simple_field(field_name: str, field_type: str = "string", **kwargs) -> dict:
        """Create V1 schema with a single field."""
        field_props = {
            "type": field_type,
            "title": field_name.replace("_", " ").title(),
        }

        if "enumNames" in kwargs:
            choices_dict = kwargs.pop("enumNames")
            field_props["enum"] = list(choices_dict.keys())
            field_props["enumNames"] = choices_dict

        field_props.update(kwargs)

        return {
            "schema": {
                "$schema": V1_DRAFT,
                "title": "Test Schema",
                "type": "object",
                "properties": {field_name: field_props},
            },
            "definition": [{"key": field_name, "htmlClass": "col-lg-6"}],
        }

    @staticmethod
    def choice_field(field_name: str, choices: dict, **kwargs) -> dict:
        """Create V1 schema with choice field using enumNames."""
        return V1SchemaBuilder.simple_field(field_name, "string", enumNames=choices, **kwargs)

    @staticmethod
    def readonly_schema(readonly_value=True, with_field=True) -> dict:
        """Create V1 schema with readonly property set.
        Args:
            readonly_value: The value for readonly (can be bool, string, number, etc.)
            with_field: Whether to include a test field in the schema
        """
        schema = {
            "$schema": V1_DRAFT,
            "title": "Test Schema",
            "type": "object",
            "readonly": readonly_value,
        }
        if with_field:
            schema["properties"] = {"test": {"type": "string", "title": "Test"}}
        else:
            schema["properties"] = {}
        return {"schema": schema, "definition": [{"key": "test", "htmlClass": "col-lg-6"}] if with_field else []}

    @staticmethod
    def invalid_schema(schema_type="malformed_json") -> Optional[str]:
        """Create various invalid schema formats for testing error handling.
        Args:
            schema_type: Type of invalid schema to create
        """
        if schema_type == "malformed_json":
            return '{"schema": {"readonly": true, "invalid": }'
        elif schema_type == "no_schema_key":
            return json.dumps({"definition": []})
        elif schema_type == "empty_string":
            return ""
        elif schema_type == "none":
            return None
        elif schema_type == "missing_schema_wrapper":
            return json.dumps({"properties": {"field": {"type": "string"}}, "readonly": True})
        else:
            raise ValueError(f"Unknown invalid schema type: {schema_type}")

    @staticmethod
    def multi_field(fields: dict):
        """Create V1 schema with multiple fields."""

        properties = {}
        for field_name, field_config in fields.items():
            properties[field_name] = {
                "type": field_config.get("type", "string"),
                "title": field_name.replace("_", " ").title(),
                **{k: v for k, v in field_config.items() if k not in ["type", "title"]},
            }

        return {
            "schema": {
                "$schema": V1_DRAFT,
                "title": "Multi-Field Test Schema",
                "type": "object",
                "properties": properties,
            },
            "definition": [{"key": name, "htmlClass": "col-lg-6"} for name in fields.keys()],
        }


class V2SchemaBuilder:
    """Builder for V2 EventType schemas with fluent interface."""

    @staticmethod
    def simple_field(field_name: str, field_type: str = "string", **kwargs) -> dict:
        """Create V2 schema with a single field."""
        field_config = {
            "deprecated": False,
            "description": "",
            "title": field_name.replace("_", " ").title(),
            "type": field_type,
            **kwargs,
        }
        return {
            "json": {
                "$schema": V2_DRAFT,
                "additionalProperties": False,
                "type": "object",
                "properties": {
                    field_name: field_config,
                },
                "required": [],
            },
            "ui": V2SchemaBuilder._ui_section(field_name, field_config),
        }

    @staticmethod
    def choice_field(field_name: str, choices: dict, **kwargs) -> dict:
        """Create V2 schema with oneOf choice structure."""
        one_of_choices = [{"const": key, "title": value} for key, value in choices.items()]
        field_config = {
            "deprecated": False,
            "description": "",
            "title": field_name.replace("_", " ").title(),
            "type": "string",
            "anyOf": [{"oneOf": one_of_choices}],
            **kwargs,
        }
        return {
            "json": {
                "$schema": V2_DRAFT,
                "additionalProperties": False,
                "type": "object",
                "properties": {
                    field_name: field_config,
                },
                "required": [],
            },
            "ui": V2SchemaBuilder._ui_section(field_name, field_config),
        }

    @staticmethod
    def choice_list_field(field_name: str, choices: dict, **kwargs) -> dict:
        """Create V2 schema with a multi-select choice list field (type=array, uniqueItems=true)."""
        one_of_choices = [{"const": key, "title": value} for key, value in choices.items()]
        field_config = {
            "deprecated": False,
            "description": "",
            "title": field_name.replace("_", " ").title(),
            "type": "array",
            "uniqueItems": True,
            "items": {
                "type": "string",
                "anyOf": [{"oneOf": one_of_choices}],
            },
            **kwargs,
        }
        return {
            "json": {
                "$schema": V2_DRAFT,
                "additionalProperties": False,
                "type": "object",
                "properties": {
                    field_name: field_config,
                },
                "required": [],
            },
            "ui": V2SchemaBuilder._ui_section(field_name, field_config),
        }

    @staticmethod
    def multi_field(fields: dict) -> dict:
        """Create V2 schema with multiple fields.

        Args:
            fields: {field_name: {"type": "string", "title": "Title", ...}}
        """
        properties = {}
        ui_fields = {}
        left_column = []

        for field_name, field_config in fields.items():
            field_type = field_config.get("type", "string")
            properties[field_name] = {
                "deprecated": False,
                "description": "",
                "title": field_config.get("title", field_name.replace("_", " ").title()),
                "type": field_type,
                **V2SchemaBuilder._clear_field_config(field_config),
            }
            if "choices" in field_config:
                properties[field_name]["anyOf"] = [
                    {"oneOf": [{"const": k, "title": v} for k, v in field_config["choices"].items()]}
                ]
            if "existing_choices" in field_config:
                existing_choices = field_config["existing_choices"]
                if isinstance(existing_choices, list):
                    existing_choices = ",".join(existing_choices)
                properties[field_name]["anyOf"] = [{"$ref": f"{reverse('schemas:choices')}?field={existing_choices}"}]
            ui_fields[field_name] = V2SchemaBuilder._field_ui_config(field_name, field_config)
            left_column.append({"name": field_name, "type": "field"})

        return {
            "json": {
                "$schema": V2_DRAFT,
                "additionalProperties": False,
                "type": "object",
                "properties": properties,
                "required": [],
            },
            "ui": {
                "fields": ui_fields,
                "headers": {},
                "order": ["section-1"],
                "sections": {
                    "section-1": {
                        "columns": 1,
                        "isActive": True,
                        "label": "",
                        "leftColumn": left_column,
                        "rightColumn": [],
                    }
                },
            },
        }

    @staticmethod
    def _clear_field_config(field_config: dict):
        return {k: v for k, v in field_config.items() if k not in ["type", "choices", "existing_choices"]}

    @staticmethod
    def _ui_section(field_name: str, field_config: dict):
        """Create UI section for a single field."""
        return {
            "fields": {field_name: V2SchemaBuilder._field_ui_config(field_name, field_config)},
            "headers": {},
            "order": ["section-1"],
            "sections": {
                "section-1": {
                    "columns": 1,
                    "isActive": True,
                    "label": "",
                    "leftColumn": [{"name": field_name, "type": "field"}],
                    "rightColumn": [],
                }
            },
        }

    @staticmethod
    def _field_ui_config(field_name: str, field_config: dict):
        """Generate UI config for a field based on type."""
        field_type = field_config.get("type", "string")

        if "existing_choices" in field_config:
            existing_choices = field_config["existing_choices"]
            if isinstance(existing_choices, str):
                existing_choices = [existing_choices]
            return {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": existing_choices,
                    "featureCategories": [],
                    "myDataType": "",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "inputType": "DROPDOWN",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            }
        elif field_type == "number":
            return {"inputType": "NUMBER", "placeholder": "", "type": "NUMBER", "parent": "section-1"}
        else:
            return {"inputType": "TEXT", "placeholder": "", "type": "TEXT", "parent": "section-1"}


class EventTypeTestHelpers:
    """DRY helper methods for EventType testing."""

    @staticmethod
    def assert_variable_generation(event_types, expected_variables):
        """Assert variable generation results."""
        variables_class, applies_to = _generate_aggregate_event_variables_class(event_types)

        for var_name in expected_variables:
            assert var_name in applies_to, f"Expected variable '{var_name}' not found in {list(applies_to.keys())}"

        return variables_class, applies_to

    @staticmethod
    def assert_choice_options(variables_class, field_name, expected_choices):
        """Assert choice options properly extracted."""
        exported_rule_data = export_rule_data(variables_class, EventActions)
        variables = exported_rule_data["variables"]

        choice_var = next((v for v in variables if field_name in v["name"]), None)
        assert choice_var is not None, f"Choice variable for {field_name} not found"

        if "options" in choice_var:
            option_values = [opt["name"] for opt in choice_var["options"]]
            for choice in expected_choices:
                assert choice in option_values, f"Expected choice '{choice}' not found in {option_values}"
