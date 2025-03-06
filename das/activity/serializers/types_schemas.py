main_event_type_schema = {
    "$id": "https://earthranger.com/event_type_v2.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Event Type V2 schema for EventType Builder",
    "properties": {
        "json": {
            "$id": "https://earthranger.com/event_type_v2.json",
            "$schema": "http://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "type": "object",
            "title": "Event Type V2 schema for EventType Builder",
            "properties": {
                "type": "object",
                "patternProperties": {
                    ".*": {
                        "anyOf": [
                            {"$ref": "https://earthranger.com/text_field.json"},
                            {"$ref": "https://earthranger.com/attachment_field.json"},
                            {"$ref": "https://earthranger.com/collection_field.json"},
                            {"$ref": "https://earthranger.com/date_time_field.json"},
                            {"$ref": "https://earthranger.com/location_field.json"},
                            {"$ref": "https://earthranger.com/numeric_field.json"},
                            {"$ref": "https://earthranger.com/choice_field.json"},
                        ]
                    }
                },
            },
        },
        "ui": {"type": "object"},
    },
}

text_field_schema = {
    "$id": "https://earthranger.com/text_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Text schema for EventType Builder",
    "properties": {
        "default": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "type": {"const": "string"},
        "additionalProperties": False,
    },
    "required": ["deprecated", "description", "title", "type"],
}

attachment_field_schema = {
    "$id": "https://earthranger.com/attachment_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Attachment field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "format": {"const": "uri"},
        "title": {"type": "string"},
        "type": {"const": "string"},
        "additionalProperties": False,
    },
    "required": ["deprecated", "title", "type", "format"],
}

collection_field_schema = {
    "$id": "https://earthranger.com/collection_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "array",
    "title": "Collection field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "items": {
            "type": {"const": "object"},
            "required": {"type": "array"},
            "properties": {"type": "object"},
            "additionalProperties": False,
        },
        "title": {"type": "string"},
        "type": {"const": "array"},
        "unevaluatedItems": {"type": "boolean"},
        "maxItems": {"type": "integer"},
        "minItems": {"type": "integer"},
        "additionalProperties": False,
    },
}

date_time_field_schema = {
    "$id": "https://earthranger.com/date_time_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "format": {"type": "string", "enum": ["date-time", "date", "time"]},
        "default": {"type": "string"},
        "title": {"type": "string"},
        "type": {"const": "string"},
        "additionalProperties": False,
    },
}

location_field_schema = {
    "$id": "https://earthranger.com/location_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Location field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "type": {"const": "object"},
        "properties": {
            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
            "longitude": {"type": "number", "minimum": -180, "maximum": 180},
            "additionalProperties": False,
        },
        "additionalProperties": False,
    },
    "required": ["deprecated", "description", "title", "type", "properties"],
}

numeric_field_schema = {
    "$id": "https://earthranger.com/numeric_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Numeric field schema for EventType Builder",
    "properties": {
        "default": {"type": "number"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "type": {"const": "number"},
        "maximum": {"type": "number"},
        "minimum": {"type": "number"},
        "additionalProperties": False,
    },
    "required": ["deprecated", "description", "title", "type"],
}

choice_any_of_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"$ref": {"type": "string", "format": "uri"}},
        "required": ["$ref"],
        "additionalProperties": False,
    },
    "minItems": 1,
}

choice_field_schema = {
    "$id": "https://earthranger.com/choice_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Choice field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "type": {"const": "string"},
        "anyOf": choice_any_of_schema,
        "additionalProperties": False,
    },
    "required": ["deprecated", "description", "title", "type", "anyOf"],
}

choice_list_field_schema = {
    "$id": "https://earthranger.com/choice_list_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Choice list field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "type": {"const": "array"},
        "items": {
            "items": choice_any_of_schema,
            "type": "array",
            "additionalItems": False,
        },
        "additionalProperties": False,
        "uniqueItems": True,
    },
    "required": ["deprecated", "description", "title", "type", "items"],
}
