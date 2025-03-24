BASE_URL = "https://example.com/schemas/event_types"

SAMPLE_SCHEMAS = {
    "sample_event_type.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/sample_event_type.json",
        "title": "Sample Event Type",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["name", "description"],
        "additionalProperties": False,
    },
    "fire_event.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/fire_event.json",
        "title": "Fire Event Type",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "status": {"$ref": f"{BASE_URL}/status_options.json"},  # Full URI reference
            "name": {"type": "string"},
            "location": {"type": "string"},
            "suspected_cause_type": {"$ref": "#/$defs/cause_types"},  # Local fragment reference
        },
        "required": ["name", "location", "suspected_cause_type"],
        "additionalProperties": False,
        "$defs": {
            "cause_types": {
                "type": "string",
                "enum": ["fire", "flood", "earthquake", "storm"],
            },
        },
    },
    "animal_event.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/animal_event.json",
        "title": "Animal Event Type",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "status": {"$ref": f"{BASE_URL}/status_options.json"},  # Full URI reference
            "animal_type": {"type": "string", "enum": ["mammal", "bird", "reptile", "amphibian", "fish"]},
            "health_status": {"type": "string", "$ref": f"{BASE_URL}/health_status_options.json"},  # Full URI reference
            "death_reason": {
                "$ref": f"{BASE_URL}/dead_reason_options.json",  # Full URI reference
                "description": "Required only if health_status is 'dead'",
                # Overrides the description from the referenced schema
            },
            "location": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["animal_type", "health_status", "location"],
        "additionalProperties": False,
        "allOf": [
            {
                "if": {"properties": {"health_status": {"const": "dead"}}, "required": ["health_status"]},
                "then": {"required": ["death_reason"]},
            }
        ],
    },
    "nested_references.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/nested_references.json",
        "title": "Schema with Nested References",
        "type": "object",
        "properties": {
            "status": {"$ref": f"{BASE_URL}/status_options.json"},
            "fire_event": {"$ref": f"{BASE_URL}/fire_event.json"},
            "animal_event": {"$ref": f"{BASE_URL}/animal_event.json"},
        },
        "required": ["status"],
        "anyOf": [
            {"required": ["fire_event"]},
            {"required": ["animal_event"]},
        ],
        "additionalProperties": False,
    },
    "external_fragment_ref.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/external_fragment_ref.json",
        "title": "Schema with External Fragment Reference",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "status": {"$ref": f"{BASE_URL}/status_options.json"},  # Full URI reference
            "cause_types": {"$ref": f"{BASE_URL}/fire_event.json#/$defs/cause_types"},  # External fragment reference
        },
        "required": ["name", "status", "cause_types"],
        "additionalProperties": False,
    },
    "external_fragment_ref_in_defs.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/external_fragment_ref_in_defs.json",
        "title": "Schema with Reference in Definitions",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "status": {"$ref": f"{BASE_URL}/status_options.json"},  # Full URI reference
            "cause_types": {"$ref": "#/$defs/cause_types"},  # Local fragment reference
        },
        "required": ["name", "status", "cause_types"],
        "additionalProperties": False,
        "$defs": {
            "cause_types": {"$ref": f"{BASE_URL}/fire_event.json#/$defs/cause_types"}  # External fragment reference
        },
    },
    "full_uri_ref_in_defs.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/full_uri_ref_in_defs.json",
        "title": "Schema with Reference in Definitions",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "status": {"$ref": "#/$defs/status_options"},  # Local fragment reference
            "cause_types": {"$ref": f"{BASE_URL}/fire_event.json#/$defs/cause_types"},  # External fragment reference
        },
        "required": ["name", "status", "cause_types"],
        "additionalProperties": False,
        "$defs": {"status_options": {"$ref": f"{BASE_URL}/status_options.json"}},  # Full URI reference
    },
    "status_options.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/status_options.json",
        "title": "Possible Event Statuses",
        "type": "string",
        "oneOf": [
            {"const": "draft", "title": "Draft"},
            {"const": "active", "title": "Active"},
            {"const": "inactive", "title": "Inactive"},
            {"const": "archived", "title": "Archived"},
        ],
    },
    "health_status_options.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/health_status_options.json",
        "title": "Possible Health Statuses for Animals",
        "type": "string",
        "oneOf": [
            {"const": "healthy", "title": "Healthy"},
            {"const": "sick", "title": "Sick"},
            {"const": "injured", "title": "Injured"},
            {"const": "dead", "title": "Dead"},
        ],
    },
    "dead_reason_options.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URL}/dead_reason_options.json",
        "title": "Possible Reasons for Death",
        "type": "string",
        "oneOf": [
            {"const": "natural", "title": "Natural Causes"},
            {"const": "disease", "title": "Disease"},
            {"const": "accident", "title": "Accident"},
            {"const": "euthanized", "title": "Euthanized"},
            {"const": "human_action", "title": "Human Action"},
        ],
    },
}
