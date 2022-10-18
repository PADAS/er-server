"""
DRF Spectacular extensions for activity app custom fields.

This module provides OpenAPI documentation extensions for custom serializer
fields to resolve DRF Spectacular warnings.
"""

from drf_spectacular.extensions import OpenApiSerializerFieldExtension

from activity.serializers.fields.json_schema import JSONSchemaField


class JSONSchemaFieldExtension(OpenApiSerializerFieldExtension):
    """OpenAPI extension for JSONSchemaField."""

    target_class = JSONSchemaField

    def map_serializer_field(self, auto_schema, direction):
        if direction == "request":
            # Input: accepts string (JSON), dict, or bytes and validates against meta schema
            return {
                "oneOf": [
                    {"type": "string", "description": "JSON string representation of schema object"},
                    {"type": "object", "description": "Schema object with json and ui sections"},
                ],
                "description": (
                    "EventType schema definition with two main sections: "
                    '"json" containing the JSON Schema for data validation, and '
                    '"ui" containing custom UI configuration for form rendering and editing.'
                ),
                "example": {
                    "json": {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "properties": {
                            "example_field": {
                                "type": "string",
                                "title": "Example Field",
                                "description": "An example text field",
                            }
                        },
                        "required": ["example_field"],
                    },
                    "ui": {
                        "fields": {
                            "example_field": {
                                "type": "TEXT",
                                "inputType": "SHORT_TEXT",
                                "placeholder": "Enter value",
                                "parent": "section-main",
                            }
                        },
                        "headers": {},
                        "order": ["example_field"],
                        "sections": {
                            "section-main": {
                                "label": "Main Section",
                                "columns": 1,
                                "isActive": True,
                                "leftColumn": [{"name": "example_field", "type": "field"}],
                                "rightColumn": [],
                            }
                        },
                    },
                },
            }
        else:
            # Output: returns JSON string representation of the validated schema object
            return {
                "type": "string",
                "description": (
                    "JSON string representation of the EventType schema object "
                    'containing validated "json" and "ui" sections.'
                ),
                "example": '{\n  "json": {\n    "$schema": "https://json-schema.org/draft/2020-12/schema",\n    "type": "object",\n    "properties": {\n      "example_field": {\n        "type": "string",\n        "title": "Example Field"\n      }\n    }\n  },\n  "ui": {\n    "fields": {\n      "example_field": {\n        "type": "TEXT",\n        "parent": "section-main"\n      }\n    },\n    "order": ["example_field"],\n    "sections": {}\n  }\n}',
            }
