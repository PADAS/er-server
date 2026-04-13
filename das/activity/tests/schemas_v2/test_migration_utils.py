"""Tests for migration utility functions (get_field_schema_from_prop_path, rewrite_field_to_ref)."""

import pytest

from activity.schemas.migration.utils import (
    get_field_schema_from_prop_path,
    rewrite_field_to_ref,
)


class TestGetFieldSchemaFromPropPath:
    def test_handles_nested_arrays(self):
        v2_schema = {
            "json": {
                "properties": {
                    "details": {
                        "type": "array",
                        "items": {
                            "properties": {
                                "severity": {
                                    "title": "Severity",
                                    "type": "string",
                                    "anyOf": [{"title": "Hardcoded", "oneOf": [{"const": "low"}]}],
                                }
                            }
                        },
                    }
                }
            }
        }

        field_schema = get_field_schema_from_prop_path(v2_schema, ["details", "severity"])

        assert field_schema["title"] == "Severity"

    @pytest.mark.parametrize(
        ("v2_schema", "property_path", "expected_title"),
        [
            (
                {
                    "json": {
                        "properties": {
                            "details": {
                                "type": "object",
                                "properties": {
                                    "location": {
                                        "type": "object",
                                        "properties": {
                                            "severity": {
                                                "title": "Location Severity",
                                                "type": "string",
                                            }
                                        },
                                    }
                                },
                            }
                        }
                    }
                },
                ["details", "location", "severity"],
                "Location Severity",
            ),
            (
                {
                    "json": {
                        "properties": {
                            "details": {
                                "type": "object",
                                "properties": {
                                    "sections": {
                                        "type": "array",
                                        "items": {
                                            "properties": {
                                                "status": {
                                                    "title": "Section Status",
                                                    "type": "string",
                                                }
                                            }
                                        },
                                    }
                                },
                            }
                        }
                    }
                },
                ["details", "sections", "status"],
                "Section Status",
            ),
            (
                {
                    "json": {
                        "properties": {
                            "observations": {
                                "type": "array",
                                "items": {
                                    "properties": {
                                        "measurements": {
                                            "type": "array",
                                            "items": {
                                                "properties": {
                                                    "value": {
                                                        "title": "Measurement Value",
                                                        "type": "number",
                                                    }
                                                }
                                            },
                                        }
                                    }
                                },
                            }
                        }
                    }
                },
                ["observations", "measurements", "value"],
                "Measurement Value",
            ),
        ],
    )
    def test_handles_nested_structures(self, v2_schema, property_path, expected_title):
        field_schema = get_field_schema_from_prop_path(v2_schema, property_path)

        assert field_schema["title"] == expected_title


class TestRewriteFieldToRef:
    def test_replaces_anyof_and_preserves_other_keys(self, choices_base_url):
        field_schema = {
            "title": "Severity",
            "type": "string",
            "description": "How severe",
            "anyOf": [{"title": "Hardcoded", "oneOf": [{"const": "low"}]}],
        }

        rewrite_field_to_ref(field_schema, "severity")

        assert field_schema == {
            "title": "Severity",
            "type": "string",
            "description": "How severe",
            "anyOf": [{"$ref": f"{choices_base_url}?field=severity"}],
        }
