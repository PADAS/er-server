"""
Shared utilities for V1/V2 EventType schema testing.
"""

from business_rules import export_rule_data

from activity.alerting.businessrules import (
    EventActions,
    _generate_aggregate_event_variables_class,
)


class V1SchemaBuilder:
    """Builder for V1 EventType JSON schemas using DRY patterns."""

    @staticmethod
    def simple_field(field_name: str, field_type: str = "string", **kwargs):
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
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "Test Schema",
                "type": "object",
                "properties": {field_name: field_props},
            },
            "definition": [{"key": field_name, "htmlClass": "col-lg-6"}],
        }

    @staticmethod
    def choice_field(field_name: str, choices: dict, **kwargs):
        """Create V1 schema with choice field using enumNames."""
        return V1SchemaBuilder.simple_field(field_name, "string", enumNames=choices, **kwargs)

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
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "Multi-Field Test Schema",
                "type": "object",
                "properties": properties,
            },
            "definition": [{"key": name, "htmlClass": "col-lg-6"} for name in fields.keys()],
        }


class V2SchemaBuilder:
    """Builder for V2 EventType schemas with fluent interface."""

    @staticmethod
    def simple_field(field_name: str, field_type: str = "string", **kwargs):
        """Create V2 schema with a single field."""
        return {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "additionalProperties": False,
                "type": "object",
                "properties": {
                    field_name: {
                        "deprecated": False,
                        "description": "",
                        "title": field_name.replace("_", " ").title(),
                        "type": field_type,
                        **kwargs,
                    }
                },
                "required": [],
            },
            "ui": V2SchemaBuilder._ui_section(field_name, field_type),
        }

    @staticmethod
    def choice_field(field_name: str, choices: dict, **kwargs):
        """Create V2 schema with oneOf choice structure."""
        one_of_choices = [{"const": key, "title": value} for key, value in choices.items()]
        return {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "additionalProperties": False,
                "type": "object",
                "properties": {
                    field_name: {
                        "deprecated": False,
                        "description": "",
                        "title": field_name.replace("_", " ").title(),
                        "type": "string",
                        "anyOf": [{"oneOf": one_of_choices}],
                        **kwargs,
                    }
                },
                "required": [],
            },
            "ui": V2SchemaBuilder._ui_section(field_name, "choice"),
        }

    @staticmethod
    def multi_field(fields: dict):
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
                **{k: v for k, v in field_config.items() if k not in ["type", "title", "choices"]},
            }
            if "choices" in field_config:
                properties[field_name]["anyOf"] = [
                    {"oneOf": [{"const": k, "title": v} for k, v in field_config["choices"].items()]}
                ]
            ui_fields[field_name] = V2SchemaBuilder._field_ui_config(field_name, field_type)
            left_column.append({"name": field_name, "type": "field"})

        return {
            "json": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
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
    def _ui_section(field_name: str, field_type: str):
        """Create UI section for a single field."""
        return {
            "fields": {field_name: V2SchemaBuilder._field_ui_config(field_name, field_type)},
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
    def _field_ui_config(field_name: str, field_type: str):
        """Generate UI config for a field based on type."""
        if field_type == "choice":
            return {
                "choices": {
                    "eventTypeCategories": [],
                    "existingChoiceList": [],
                    "featureCategories": [],
                    "myDataType": "",
                    "subjectGroups": [],
                    "subjectSubtypes": [],
                    "type": "EXISTING_CHOICE_LIST",
                },
                "fieldType": "choice",
                "control": "select",
                "placeholder": "",
                "type": "CHOICE_LIST",
                "parent": "section-1",
            }
        elif field_type == "number":
            return {"inputType": "NUMBER", "placeholder": "", "type": "NUMBER", "parent": "section-1"}
        else:  # default to text
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


# Test Data Constants (for easy reuse across tests)
standard_choices = {"active": "Active", "inactive": "Inactive", "pending": "Pending"}

simple_choices = {"option1": "Option 1", "option2": "Option 2"}
