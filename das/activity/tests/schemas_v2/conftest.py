import json
from pathlib import Path

import pytest


@pytest.fixture
def json_schema_fixture(request):
    """Load a JSON schema fixture file by name."""
    fixture_name = request.param
    fixture_path = Path(__file__).parent.parent / "fixtures" / f"{fixture_name}.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def auto_generate_v1_marker_schema():
    """V1 auto-generate marker schema for testing (as used in Django admin)."""
    return {
        "auto-generate": True,
        "description": "This schema is a placeholder, to be replaced automatically when new data is recorded.",
        "schema": {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": "Placeholder schema",
            "type": "object",
            "readonly": True,
            "properties": {
                "placeholder": {
                    "type": "string",
                    "title": "Placeholder",
                    "default": "This schema will be auto-generated when event data is recorded.",
                }
            },
        },
        "definition": ["placeholder"],
    }


@pytest.fixture
def auto_generate_v2_marker_schema():
    """V2 auto-generate marker schema for testing."""
    return {
        "auto-generate": True,
        "description": "This schema is a placeholder, to be replaced automatically when new data is recorded.",
        "json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "properties": {
                "placeholder": {
                    "default": "This schema will be auto-generated when event data is recorded.",
                    "deprecated": False,
                    "title": "Placeholder",
                    "type": "string",
                }
            },
            "required": [],
            "type": "object",
            "unevaluatedProperties": False,
        },
        "ui": {
            "fields": {
                "placeholder": {
                    "conditionalDependents": [],
                    "inputType": "SHORT_TEXT",
                    "parent": "section-1",
                    "placeholder": "",
                    "type": "TEXT",
                }
            },
            "headers": {},
            "order": ["section-1"],
            "sections": {
                "section-1": {
                    "columns": 1,
                    "conditions": [],
                    "isActive": True,
                    "label": "",
                    "leftColumn": [{"name": "placeholder", "type": "field"}],
                    "rightColumn": [],
                }
            },
        },
    }
