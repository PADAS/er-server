"""Tests for migration utility functions (get_field_schema_from_prop_path, rewrite_field_to_ref)."""

import pytest

from activity.schemas.migration.utils import rewrite_field_to_ref
from activity.schemas.utils import get_field_schema_from_prop_path


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

    def test_intermediate_scalar_segment_returns_none(self):
        """When an intermediate path segment resolves to a scalar, traversal returns None.

        This is the sideways-jump regression: before the fix, looking up
        ["incident_title", "photo"] would resolve "incident_title" to a string
        field, then (because current_properties was not updated) match "photo"
        against the sibling top-level properties and return the sibling's schema
        instead of None.
        """
        v2_schema = {
            "json": {
                "properties": {
                    "incident_title": {
                        "title": "Incident Title",
                        "type": "string",
                    },
                    "photo": {
                        "title": "Photo",
                        "type": "array",
                        "items": {
                            "properties": {"uploadId": {"format": "uuid", "type": "string"}},
                            "required": ["uploadId"],
                            "type": "object",
                            "unevaluatedProperties": False,
                        },
                        "uniqueItems": True,
                    },
                }
            }
        }

        result = get_field_schema_from_prop_path(v2_schema, ["incident_title", "photo"])

        assert result is None, "Traversal through a scalar segment must return None, not a sibling schema"

    def test_valid_nested_path_after_scalar_fix_still_resolves(self):
        """A valid nested path (array → items.properties) still resolves correctly.

        Guards against over-correction: fixing the scalar sideways-jump must not
        break legitimate two-segment paths that descend through an array.
        """
        v2_schema = {
            "json": {
                "properties": {
                    "arrests": {
                        "title": "Arrests",
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "arrestee_photo": {
                                    "title": "Photo",
                                    "type": "array",
                                    "uniqueItems": True,
                                }
                            },
                        },
                    }
                }
            }
        }

        result = get_field_schema_from_prop_path(v2_schema, ["arrests", "arrestee_photo"])

        assert result is not None
        assert result["title"] == "Photo"


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
