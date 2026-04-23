# Constants

FIELD_PLACEHOLDER_MAX_LENGTH = 32
FIELD_TITLE_MAX_LENGTH = 1000

FORM_ELEMENT_SEGMENT_PATTERN = r"[a-zA-Z0-9_-]+"

FIELD_NAME_PATTERN = rf"^{FORM_ELEMENT_SEGMENT_PATTERN}$"
FIELD_ID_PATTERN = rf"^{FORM_ELEMENT_SEGMENT_PATTERN}(?:\.{FORM_ELEMENT_SEGMENT_PATTERN})*$"

HEADER_ID_PATTERN = rf"^header-{FORM_ELEMENT_SEGMENT_PATTERN}$"

SECTION_ID_PATTERN = rf"^section-{FORM_ELEMENT_SEGMENT_PATTERN}$"


# Shared schemas

conditional_dependents_schema = {
    "type": "array",
    "items": {"type": "string", "pattern": SECTION_ID_PATTERN},
    "uniqueItems": True,
}

field_parent_schema = {
    "anyOf": [
        {"type": "string", "pattern": FIELD_ID_PATTERN},
        {"type": "string", "pattern": SECTION_ID_PATTERN},
    ],
}


# Attachment field

attachment_field_json_schema = {
    "type": "object",
    "title": "Attachment field JSON schema",
    "properties": {
        "deprecated": {"type": "boolean"},
        "format": {"const": "uri"},
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "string"},
    },
    "required": ["deprecated", "format", "title", "type"],
    "additionalProperties": False,
}

attachment_field_ui_schema = {
    "type": "object",
    "title": "Attachment field UI schema",
    "properties": {
        "allowableFileTypes": {
            "type": "array",
            "items": {"enum": ["audio", "document", "image", "video"]},
            "uniqueItems": True,
        },
        "conditionalDependents": conditional_dependents_schema,
        "parent": field_parent_schema,
        "type": {"const": "ATTACHMENT"},
    },
    "required": ["allowableFileTypes", "parent", "type"],
    "additionalProperties": False,
}


# Boolean field

boolean_field_json_schema = {
    "type": "object",
    "title": "Boolean field JSON schema",
    "properties": {
        "default": {"type": "boolean"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "boolean"},
    },
    "required": ["deprecated", "title", "type"],
    "additionalProperties": False,
}

boolean_field_ui_schema = {
    "type": "object",
    "title": "Boolean field UI schema",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "parent": field_parent_schema,
        "type": {"const": "BOOLEAN"},
    },
    "required": ["parent", "type"],
    "additionalProperties": False,
}


# Choice List field

choice_list_field_json_schema_any_of_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "$ref": {"type": "string", "format": "uri-reference"},
        },
        "required": ["$ref"],
        "additionalProperties": False,
    },
    "minItems": 1,
}

resolved_choice_list_field_json_schema_any_of_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "oneOf": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "const": {"type": ["string", "number", "boolean"]},
                        "description": {"type": "string"},
                        "title": {"type": "string"},
                    },
                    "required": ["const", "title"],
                },
            },
            "title": {"type": "string"},
            "type": {"type": "string"},
        },
        "required": ["oneOf", "title", "type"],
    },
    "minItems": 1,
}

single_choice_list_field_json_schema = {
    "type": "object",
    "title": "Single Choice List field JSON schema",
    "properties": {
        "anyOf": {
            "anyOf": [
                choice_list_field_json_schema_any_of_schema,
                resolved_choice_list_field_json_schema_any_of_schema,
            ]
        },
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "string"},
    },
    "required": ["anyOf", "deprecated", "title", "type"],
    "additionalProperties": False,
}

multiple_choice_list_field_json_schema = {
    "type": "object",
    "title": "Multiple Choice List field JSON schema",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "items": {
            "type": "object",
            "properties": {
                "anyOf": {
                    "anyOf": [
                        choice_list_field_json_schema_any_of_schema,
                        resolved_choice_list_field_json_schema_any_of_schema,
                    ]
                },
                "type": {"const": "string"},
            },
            "required": ["anyOf", "type"],
            "additionalProperties": False,
        },
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "array"},
        "uniqueItems": {"const": True},
    },
    "required": ["deprecated", "items", "title", "type", "uniqueItems"],
    "additionalProperties": False,
}

choice_list_field_ui_schema_choices_array_schema = {"type": "array", "items": {"type": "string"}}

choice_list_field_ui_schema = {
    "type": "object",
    "title": "Choice List field UI schema",
    "properties": {
        "choices": {
            "type": "object",
            "properties": {
                "eventTypeCategories": choice_list_field_ui_schema_choices_array_schema,
                "existingChoiceList": choice_list_field_ui_schema_choices_array_schema,
                "featureCategories": choice_list_field_ui_schema_choices_array_schema,
                "myDataType": {
                    "enum": [
                        "EVENT_TYPES_FROM_EVENT_CATEGORY",
                        "FEATURES_FROM_FEATURE_CATEGORY",
                        "SOURCES",
                        "SUBJECTS_FROM_SUBJECT_GROUP",
                        "SUBJECTS_FROM_SUBJECT_SUBTYPE",
                        "USERS",
                    ],
                },
                "subjectGroups": choice_list_field_ui_schema_choices_array_schema,
                "subjectSubtypes": choice_list_field_ui_schema_choices_array_schema,
                "type": {"enum": ["EXISTING_CHOICE_LIST", "MY_DATA"]},
            },
            "required": ["type"],
            "allOf": [
                {
                    "if": {"properties": {"type": {"const": "EXISTING_CHOICE_LIST"}}, "required": ["type"]},
                    "then": {"properties": {"existingChoiceList": {"minItems": 1}}, "required": ["existingChoiceList"]},
                },
                {
                    "if": {"properties": {"type": {"const": "MY_DATA"}}, "required": ["type"]},
                    "then": {"required": ["myDataType"]},
                },
                {
                    "if": {
                        "properties": {"myDataType": {"const": "EVENT_TYPES_FROM_EVENT_CATEGORY"}},
                        "required": ["myDataType"],
                    },
                    "then": {
                        "properties": {"eventTypeCategories": {"minItems": 1}},
                        "required": ["eventTypeCategories"],
                    },
                },
                {
                    "if": {
                        "properties": {"myDataType": {"const": "FEATURES_FROM_FEATURE_CATEGORY"}},
                        "required": ["myDataType"],
                    },
                    "then": {"properties": {"featureCategories": {"minItems": 1}}, "required": ["featureCategories"]},
                },
                {
                    "if": {
                        "properties": {"myDataType": {"const": "SUBJECTS_FROM_SUBJECT_GROUP"}},
                        "required": ["myDataType"],
                    },
                    "then": {"properties": {"subjectGroups": {"minItems": 1}}, "required": ["subjectGroups"]},
                },
                {
                    "if": {
                        "properties": {"myDataType": {"const": "SUBJECTS_FROM_SUBJECT_SUBTYPE"}},
                        "required": ["myDataType"],
                    },
                    "then": {"properties": {"subjectSubtypes": {"minItems": 1}}, "required": ["subjectSubtypes"]},
                },
            ],
            "additionalProperties": False,
        },
        "conditionalDependents": conditional_dependents_schema,
        "inputType": {"enum": ["DROPDOWN", "LIST"]},
        "placeholder": {"type": "string", "maxLength": FIELD_PLACEHOLDER_MAX_LENGTH},
        "parent": field_parent_schema,
        "type": {"const": "CHOICE_LIST"},
    },
    "required": ["choices", "inputType", "parent", "type"],
    "additionalProperties": False,
}


# Date time field

date_time_field_json_schema = {
    "type": "object",
    "title": "Date Time field JSON schema",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "format": {"enum": ["date-time", "date", "time"]},
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "string"},
    },
    "required": ["deprecated", "format", "title", "type"],
    "additionalProperties": False,
}

date_time_field_ui_schema = {
    "type": "object",
    "title": "Date Time field UI schema",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "parent": field_parent_schema,
        "type": {"const": "DATE_TIME"},
    },
    "required": ["parent", "type"],
    "additionalProperties": False,
}


# Location field

location_field_json_schema = {
    "type": "object",
    "title": "Location field JSON schema",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "properties": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "object",
                    "properties": {
                        "maximum": {"const": 90},
                        "minimum": {"const": -90},
                        "type": {"const": "number"},
                    },
                    "required": ["maximum", "minimum", "type"],
                    "additionalProperties": False,
                },
                "longitude": {
                    "type": "object",
                    "properties": {
                        "maximum": {"const": 180},
                        "minimum": {"const": -180},
                        "type": {"const": "number"},
                    },
                    "required": ["maximum", "minimum", "type"],
                    "additionalProperties": False,
                },
            },
            "required": ["latitude", "longitude"],
            "additionalProperties": False,
        },
        "required": {
            "type": "array",
            "items": {"enum": ["latitude", "longitude"]},
            "minItems": 2,
            "maxItems": 2,
            "uniqueItems": True,
        },
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "object"},
        "unevaluatedProperties": {"const": False},
    },
    "required": ["deprecated", "properties", "required", "title", "type", "unevaluatedProperties"],
    "additionalProperties": False,
}

location_field_ui_schema = {
    "type": "object",
    "title": "Location field UI schema",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "parent": field_parent_schema,
        "type": {"const": "LOCATION"},
    },
    "required": ["parent", "type"],
    "additionalProperties": False,
}


# Numeric field

numeric_field_json_schema = {
    "type": "object",
    "title": "Numeric field JSON schema",
    "properties": {
        "default": {"type": "number"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "maximum": {"type": "number"},
        "minimum": {"type": "number"},
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "number"},
    },
    "required": ["deprecated", "title", "type"],
    "additionalProperties": False,
}

numeric_field_ui_schema = {
    "type": "object",
    "title": "Numeric field UI schema",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "parent": field_parent_schema,
        "placeholder": {"type": "string", "maxLength": FIELD_PLACEHOLDER_MAX_LENGTH},
        "type": {"const": "NUMERIC"},
    },
    "required": ["parent", "type"],
    "additionalProperties": False,
}


# Text field

text_field_json_schema = {
    "type": "object",
    "title": "Text field JSON schema",
    "properties": {
        "default": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "format": {"enum": ["uri", "uuid", "email"]},
        "pattern": {"const": "^[a-zA-Z0-9]+$"},
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "string"},
    },
    "required": ["deprecated", "title", "type"],
    "additionalProperties": False,
}

text_field_ui_schema = {
    "type": "object",
    "title": "Text field UI schema",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "inputType": {"enum": ["LONG_TEXT", "SHORT_TEXT"]},
        "parent": field_parent_schema,
        "placeholder": {"type": "string", "maxLength": FIELD_PLACEHOLDER_MAX_LENGTH},
        "type": {"const": "TEXT"},
    },
    "required": ["inputType", "parent", "type"],
    "additionalProperties": False,
}


# Collection field

collection_field_json_schema = {
    "type": "object",
    "title": "Collection field JSON schema",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "items": {
            "type": "object",
            "properties": {
                "properties": {
                    "type": "object",
                    "patternProperties": {
                        FIELD_NAME_PATTERN: {
                            "anyOf": [
                                {"$ref": "#/$defs/attachmentFieldJSONSchema"},
                                {"$ref": "#/$defs/booleanFieldJSONSchema"},
                                {"$ref": "#/$defs/collectionFieldJSONSchema"},
                                {"$ref": "#/$defs/dateTimeFieldJSONSchema"},
                                {"$ref": "#/$defs/locationFieldJSONSchema"},
                                {"$ref": "#/$defs/multipleChoiceListFieldJSONSchema"},
                                {"$ref": "#/$defs/numericFieldJSONSchema"},
                                {"$ref": "#/$defs/singleChoiceListFieldJSONSchema"},
                                {"$ref": "#/$defs/textFieldJSONSchema"},
                            ]
                        }
                    },
                    "additionalProperties": False,
                },
                "required": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": FIELD_NAME_PATTERN,
                    },
                    "uniqueItems": True,
                },
                "type": {"const": "object"},
                "unevaluatedProperties": {"const": False},
            },
            "required": ["properties", "required", "type", "unevaluatedProperties"],
        },
        "maxItems": {"type": "integer"},
        "minItems": {"type": "integer"},
        "title": {"type": "string", "maxLength": FIELD_TITLE_MAX_LENGTH},
        "type": {"const": "array"},
        "unevaluatedItems": {"const": False},
    },
    "required": ["deprecated", "items", "title", "type", "unevaluatedItems"],
    "additionalProperties": False,
}

COLLECTION_FIELD_BUTTON_TEXT_MAX_LENGTH = 50
COLLECTION_FIELD_ITEM_NAME_MAX_LENGTH = 100

collection_field_ui_schema_column_schema = {
    "type": "array",
    "items": {"type": "string", "pattern": FIELD_ID_PATTERN},
    "uniqueItems": True,
}

collection_field_ui_schema = {
    "type": "object",
    "title": "Collection field UI schema",
    "properties": {
        "buttonText": {"type": "string", "maxLength": COLLECTION_FIELD_BUTTON_TEXT_MAX_LENGTH},
        "columns": {"enum": [1, 2]},
        "conditionalDependents": conditional_dependents_schema,
        "itemIdentifier": {
            "anyOf": [
                {"const": ""},
                {"type": "string", "pattern": FIELD_ID_PATTERN},
            ],
        },
        "itemName": {"type": "string", "maxLength": COLLECTION_FIELD_ITEM_NAME_MAX_LENGTH},
        "leftColumn": collection_field_ui_schema_column_schema,
        "parent": field_parent_schema,
        "rightColumn": collection_field_ui_schema_column_schema,
        "type": {"const": "COLLECTION"},
    },
    "required": ["columns", "itemName", "leftColumn", "parent", "rightColumn", "type"],
    "additionalProperties": False,
}


# Header

header_ui_schema = {
    "type": "object",
    "title": "Header UI schema",
    "properties": {
        "label": {"type": "string"},
        "section": {"type": "string", "pattern": SECTION_ID_PATTERN},
        "size": {"enum": ["LARGE", "MEDIUM", "SMALL"]},
    },
    "required": ["label", "section", "size"],
    "additionalProperties": False,
}


# Section

section_ui_schema_column_schema = {
    "type": "array",
    "items": {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "pattern": HEADER_ID_PATTERN},
                    "type": {"const": "header"},
                },
                "required": ["name", "type"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "pattern": FIELD_ID_PATTERN},
                    "type": {"const": "field"},
                },
                "required": ["name", "type"],
                "additionalProperties": False,
            },
        ]
    },
    "uniqueItems": True,
}

section_ui_schema = {
    "type": "object",
    "title": "Section UI schema",
    "properties": {
        "columns": {"enum": [1, 2]},
        "conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "pattern": FIELD_NAME_PATTERN},
                    "id": {"type": "string", "pattern": "^condition-.+$"},
                    "operator": {
                        "enum": [
                            "CONTAINS",
                            "IS_CONTAINED_BY",
                            "IS_NOT_CONTAINED_BY",
                            "IS_EMPTY",
                            "IS_NOT_EMPTY",
                            "IS_EXACTLY",
                        ]
                    },
                    "value": {
                        "anyOf": [{"type": "string"}, {"type": "null"}, {"type": "array", "items": {"type": "string"}}]
                    },
                },
                "required": ["field", "id", "operator"],
                "additionalProperties": False,
            },
        },
        "isActive": {"type": "boolean"},
        "label": {"type": "string"},
        "leftColumn": section_ui_schema_column_schema,
        "rightColumn": section_ui_schema_column_schema,
    },
    "required": ["columns", "isActive", "leftColumn", "rightColumn"],
    "additionalProperties": False,
}


# Contains condition

contains_condition_schema = {
    "type": "object",
    "title": "Contains condition schema",
    "properties": {
        "properties": {
            "type": "object",
            "patternProperties": {
                FIELD_NAME_PATTERN: {
                    "type": "object",
                    "properties": {
                        "anyOf": {
                            "type": "array",
                            "prefixItems": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "allOf": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "contains": {
                                                        "type": "object",
                                                        "properties": {"const": {"type": "string"}},
                                                        "required": ["const"],
                                                        "additionalProperties": False,
                                                    }
                                                },
                                                "required": ["contains"],
                                                "additionalProperties": False,
                                            },
                                            "minItems": 1,
                                        },
                                        "type": {"const": "array"},
                                    },
                                    "required": ["allOf", "type"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                        "type": {"const": "object"},
                                    },
                                    "required": ["required", "type"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "const": {"type": "null"},
                                        "pattern": {"type": "string"},
                                        "type": {"const": "string"},
                                    },
                                    "oneOf": [{"required": ["pattern", "type"]}, {"required": ["const", "type"]}],
                                    "additionalProperties": False,
                                },
                            ],
                            "minItems": 3,
                            "maxItems": 3,
                            "items": False,
                        }
                    },
                    "required": ["anyOf"],
                    "additionalProperties": False,
                }
            },
            "minProperties": 1,
            "maxProperties": 1,
            "additionalProperties": False,
        },
        "required": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": FIELD_NAME_PATTERN,
            },
            "maxItems": 1,
            "minItems": 1,
        },
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}


# Is Empty condition

is_empty_condition_schema = {
    "type": "object",
    "title": "Is Empty condition schema",
    "properties": {
        "anyOf": {
            "type": "array",
            "prefixItems": [
                {
                    "type": "object",
                    "properties": {
                        "not": {
                            "type": "object",
                            "properties": {
                                "required": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "pattern": FIELD_NAME_PATTERN,
                                    },
                                    "minItems": 1,
                                    "maxItems": 1,
                                }
                            },
                            "required": ["required"],
                            "additionalProperties": False,
                        }
                    },
                    "required": ["not"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "properties": {
                            "type": "object",
                            "patternProperties": {
                                FIELD_NAME_PATTERN: {
                                    "type": "object",
                                    "properties": {"maxItems": {"const": 0}, "type": {"const": "array"}},
                                    "required": ["maxItems", "type"],
                                    "additionalProperties": False,
                                }
                            },
                            "minProperties": 1,
                            "maxProperties": 1,
                            "additionalProperties": False,
                        },
                        "required": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "pattern": FIELD_NAME_PATTERN,
                            },
                            "minItems": 1,
                            "maxItems": 1,
                        },
                    },
                    "required": ["properties", "required"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "properties": {
                            "type": "object",
                            "patternProperties": {
                                FIELD_NAME_PATTERN: {
                                    "type": "object",
                                    "properties": {"type": {"const": "null"}},
                                    "required": ["type"],
                                    "additionalProperties": False,
                                }
                            },
                            "minProperties": 1,
                            "maxProperties": 1,
                            "additionalProperties": False,
                        },
                        "required": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "pattern": FIELD_NAME_PATTERN,
                            },
                            "minItems": 1,
                            "maxItems": 1,
                        },
                    },
                    "required": ["properties", "required"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "properties": {
                            "type": "object",
                            "patternProperties": {
                                FIELD_NAME_PATTERN: {
                                    "type": "object",
                                    "properties": {"maxProperties": {"const": 0}, "type": {"const": "object"}},
                                    "required": ["maxProperties", "type"],
                                    "additionalProperties": False,
                                }
                            },
                            "minProperties": 1,
                            "maxProperties": 1,
                            "additionalProperties": False,
                        },
                        "required": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "pattern": FIELD_NAME_PATTERN,
                            },
                            "minItems": 1,
                            "maxItems": 1,
                        },
                    },
                    "required": ["properties", "required"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "properties": {
                            "type": "object",
                            "patternProperties": {
                                FIELD_NAME_PATTERN: {
                                    "type": "object",
                                    "properties": {"maxLength": {"const": 0}, "type": {"const": "string"}},
                                    "required": ["maxLength", "type"],
                                    "additionalProperties": False,
                                }
                            },
                            "minProperties": 1,
                            "maxProperties": 1,
                            "additionalProperties": False,
                        },
                        "required": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "pattern": FIELD_NAME_PATTERN,
                            },
                            "minItems": 1,
                            "maxItems": 1,
                        },
                    },
                    "required": ["properties", "required"],
                    "additionalProperties": False,
                },
            ],
            "minItems": 5,
            "maxItems": 5,
            "items": False,
        }
    },
    "required": ["anyOf"],
    "additionalProperties": False,
}


# Is Not Empty condition

is_not_empty_condition_schema = {
    "type": "object",
    "title": "Is Not Empty condition schema",
    "properties": {
        "properties": {
            "type": "object",
            "patternProperties": {
                FIELD_NAME_PATTERN: {
                    "type": "object",
                    "properties": {
                        "allOf": {
                            "type": "array",
                            "prefixItems": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "not": {
                                            "type": "object",
                                            "properties": {"type": {"const": "null"}},
                                            "required": ["type"],
                                            "additionalProperties": False,
                                        }
                                    },
                                    "required": ["not"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "anyOf": {
                                            "type": "array",
                                            "prefixItems": [
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "minItems": {"const": 1},
                                                        "type": {"const": "array"},
                                                    },
                                                    "required": ["minItems", "type"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {"type": {"const": "boolean"}},
                                                    "required": ["type"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {"type": {"const": "number"}},
                                                    "required": ["type"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "minProperties": {"const": 1},
                                                        "type": {"const": "object"},
                                                    },
                                                    "required": ["minProperties", "type"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "minLength": {"const": 1},
                                                        "type": {"const": "string"},
                                                    },
                                                    "required": ["minLength", "type"],
                                                    "additionalProperties": False,
                                                },
                                            ],
                                            "minItems": 5,
                                            "maxItems": 5,
                                            "items": False,
                                        }
                                    },
                                    "required": ["anyOf"],
                                    "additionalProperties": False,
                                },
                            ],
                            "minItems": 2,
                            "maxItems": 2,
                            "items": False,
                        }
                    },
                    "required": ["allOf"],
                    "additionalProperties": False,
                }
            },
            "minProperties": 1,
            "maxProperties": 1,
            "additionalProperties": False,
        },
        "required": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": FIELD_NAME_PATTERN,
            },
            "minItems": 1,
            "maxItems": 1,
        },
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}


# Is Exactly condition

is_exactly_condition_schema = {
    "type": "object",
    "title": "Is Exactly condition schema",
    "properties": {
        "properties": {
            "type": "object",
            "patternProperties": {
                FIELD_NAME_PATTERN: {
                    "type": "object",
                    "properties": {
                        "anyOf": {
                            "type": "array",
                            "prefixItems": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "allOf": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "contains": {
                                                        "type": "object",
                                                        "properties": {"const": {"type": "string"}},
                                                        "required": ["const"],
                                                        "additionalProperties": False,
                                                    }
                                                },
                                                "required": ["contains"],
                                                "additionalProperties": False,
                                            },
                                            "minItems": 1,
                                        },
                                        "maxItems": {"type": "integer"},
                                        "type": {"const": "array"},
                                    },
                                    "required": ["allOf", "maxItems", "type"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "const": {"type": ["boolean", "null"]},
                                        "type": {"const": "boolean"},
                                    },
                                    "required": ["const", "type"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {"const": {"type": ["number", "null"]}, "type": {"const": "number"}},
                                    "required": ["const", "type"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "properties": {
                                            "type": "object",
                                            "additionalProperties": {"type": "object", "maxProperties": 0},
                                        },
                                        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                        "type": {"const": "object"},
                                        "unevaluatedProperties": {"const": False},
                                    },
                                    "required": ["properties", "required", "type", "unevaluatedProperties"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {"const": {"type": ["string", "null"]}, "type": {"const": "string"}},
                                    "required": ["const", "type"],
                                    "additionalProperties": False,
                                },
                            ],
                            "minItems": 5,
                            "maxItems": 5,
                            "items": False,
                        }
                    },
                    "required": ["anyOf"],
                    "additionalProperties": False,
                }
            },
            "minProperties": 1,
            "maxProperties": 1,
            "additionalProperties": False,
        },
        "required": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": FIELD_NAME_PATTERN,
            },
            "minItems": 1,
            "maxItems": 1,
        },
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}


# Is Contained By condition

is_contained_by_condition_schema = {
    "type": "object",
    "title": "Is Contained By condition schema",
    "properties": {
        "properties": {
            "type": "object",
            "patternProperties": {
                FIELD_NAME_PATTERN: {
                    "type": "object",
                    "properties": {
                        "anyOf": {
                            "type": "array",
                            "prefixItems": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "enum": {"type": "array", "items": {"type": "string"}, "minItems": 1}
                                            },
                                            "required": ["enum"],
                                            "additionalProperties": False,
                                        },
                                        "minItems": {"const": 1},
                                        "type": {"const": "array"},
                                    },
                                    "required": ["items", "minItems", "type"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "minProperties": {"const": 1},
                                        "propertyNames": {
                                            "type": "object",
                                            "properties": {
                                                "enum": {"type": "array", "items": {"type": "string"}, "minItems": 1}
                                            },
                                            "required": ["enum"],
                                            "additionalProperties": False,
                                        },
                                        "type": {"const": "object"},
                                    },
                                    "required": ["minProperties", "propertyNames", "type"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "enum": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                                        "type": {"const": "string"},
                                    },
                                    "required": ["enum", "type"],
                                    "additionalProperties": False,
                                },
                            ],
                            "minItems": 3,
                            "maxItems": 3,
                            "items": False,
                        }
                    },
                    "required": ["anyOf"],
                    "additionalProperties": False,
                }
            },
            "minProperties": 1,
            "maxProperties": 1,
            "additionalProperties": False,
        },
        "required": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": FIELD_NAME_PATTERN,
            },
            "minItems": 1,
            "maxItems": 1,
        },
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}


# Is Not Contained By condition

is_not_contained_by_condition_schema = {
    "type": "object",
    "title": "Is Not Contained By condition schema",
    "properties": {
        "properties": {
            "type": "object",
            "patternProperties": {
                FIELD_NAME_PATTERN: {
                    "type": "object",
                    "properties": {
                        "anyOf": {
                            "type": "array",
                            "prefixItems": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "allOf": {
                                            "type": "array",
                                            "prefixItems": [
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "minItems": {"const": 1},
                                                        "type": {"const": "array"},
                                                    },
                                                    "required": ["minItems", "type"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "not": {
                                                            "type": "object",
                                                            "properties": {
                                                                "items": {
                                                                    "type": "object",
                                                                    "properties": {
                                                                        "enum": {
                                                                            "type": "array",
                                                                            "items": {"type": "string"},
                                                                            "minItems": 1,
                                                                        }
                                                                    },
                                                                    "required": ["enum"],
                                                                    "additionalProperties": False,
                                                                },
                                                                "type": {"const": "array"},
                                                            },
                                                            "required": ["items", "type"],
                                                            "additionalProperties": False,
                                                        }
                                                    },
                                                    "required": ["not"],
                                                    "additionalProperties": False,
                                                },
                                            ],
                                            "minItems": 2,
                                            "maxItems": 2,
                                            "items": False,
                                        }
                                    },
                                    "required": ["allOf"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "allOf": {
                                            "type": "array",
                                            "prefixItems": [
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "minProperties": {"const": 1},
                                                        "type": {"const": "object"},
                                                    },
                                                    "required": ["minProperties", "type"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "not": {
                                                            "type": "object",
                                                            "properties": {
                                                                "propertyNames": {
                                                                    "type": "object",
                                                                    "properties": {
                                                                        "enum": {
                                                                            "type": "array",
                                                                            "items": {"type": "string"},
                                                                            "minItems": 1,
                                                                        }
                                                                    },
                                                                    "required": ["enum"],
                                                                    "additionalProperties": False,
                                                                },
                                                                "type": {"const": "object"},
                                                            },
                                                            "required": ["propertyNames", "type"],
                                                            "additionalProperties": False,
                                                        }
                                                    },
                                                    "required": ["not"],
                                                    "additionalProperties": False,
                                                },
                                            ],
                                            "minItems": 2,
                                            "maxItems": 2,
                                            "items": False,
                                        }
                                    },
                                    "required": ["allOf"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "not": {
                                            "type": "object",
                                            "properties": {
                                                "enum": {"type": "array", "items": {"type": "string"}, "minItems": 1}
                                            },
                                            "required": ["enum"],
                                            "additionalProperties": False,
                                        },
                                        "type": {"const": "string"},
                                    },
                                    "required": ["not", "type"],
                                    "additionalProperties": False,
                                },
                            ],
                            "minItems": 3,
                            "maxItems": 3,
                            "items": False,
                        }
                    },
                    "required": ["anyOf"],
                    "additionalProperties": False,
                }
            },
            "minProperties": 1,
            "maxProperties": 1,
            "additionalProperties": False,
        },
        "required": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": FIELD_NAME_PATTERN,
            },
            "minItems": 1,
            "maxItems": 1,
        },
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}


# UI

ui_schema = {
    "type": "object",
    "title": "UI schema",
    "properties": {
        "fields": {
            "type": "object",
            "patternProperties": {
                FIELD_ID_PATTERN: {
                    "anyOf": [
                        {"$ref": "#/$defs/attachmentFieldUISchema"},
                        {"$ref": "#/$defs/booleanFieldUISchema"},
                        {"$ref": "#/$defs/choiceListFieldUISchema"},
                        {"$ref": "#/$defs/collectionFieldUISchema"},
                        {"$ref": "#/$defs/dateTimeFieldUISchema"},
                        {"$ref": "#/$defs/locationFieldUISchema"},
                        {"$ref": "#/$defs/numericFieldUISchema"},
                        {"$ref": "#/$defs/textFieldUISchema"},
                    ]
                }
            },
            "additionalProperties": False,
        },
        "headers": {
            "type": "object",
            "patternProperties": {
                HEADER_ID_PATTERN: {"$ref": "#/$defs/headerUISchema"},
            },
            "additionalProperties": False,
        },
        "order": {
            "type": "array",
            "items": {"type": "string", "pattern": SECTION_ID_PATTERN},
            "uniqueItems": True,
        },
        "sections": {
            "type": "object",
            "patternProperties": {
                SECTION_ID_PATTERN: {"$ref": "#/$defs/sectionUISchema"},
            },
            "additionalProperties": False,
        },
    },
    "required": ["fields", "headers", "order", "sections"],
    "additionalProperties": False,
}


# JSON

json_field_schema = {
    "type": "object",
    "title": "JSON schema",
    "properties": {
        "$schema": {"const": "https://json-schema.org/draft/2020-12/schema"},
        "allOf": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "if": {
                        "type": "object",
                        "properties": {
                            "allOf": {
                                "type": "array",
                                "items": {
                                    "anyOf": [
                                        {"$ref": "#/$defs/containsConditionSchema"},
                                        {"$ref": "#/$defs/isEmptyConditionSchema"},
                                        {"$ref": "#/$defs/isNotEmptyConditionSchema"},
                                        {"$ref": "#/$defs/isExactlyConditionSchema"},
                                        {"$ref": "#/$defs/isContainedByConditionSchema"},
                                        {"$ref": "#/$defs/isNotContainedByConditionSchema"},
                                    ]
                                },
                            }
                        },
                        "required": ["allOf"],
                        "additionalProperties": False,
                    },
                    "then": {
                        "type": "object",
                        "properties": {
                            "properties": {
                                "type": "object",
                                "patternProperties": {
                                    FIELD_NAME_PATTERN: {
                                        "anyOf": [
                                            {"$ref": "#/$defs/attachmentFieldJSONSchema"},
                                            {"$ref": "#/$defs/booleanFieldJSONSchema"},
                                            {"$ref": "#/$defs/collectionFieldJSONSchema"},
                                            {"$ref": "#/$defs/dateTimeFieldJSONSchema"},
                                            {"$ref": "#/$defs/locationFieldJSONSchema"},
                                            {"$ref": "#/$defs/multipleChoiceListFieldJSONSchema"},
                                            {"$ref": "#/$defs/numericFieldJSONSchema"},
                                            {"$ref": "#/$defs/singleChoiceListFieldJSONSchema"},
                                            {"$ref": "#/$defs/textFieldJSONSchema"},
                                        ]
                                    }
                                },
                                "additionalProperties": False,
                            },
                            "required": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "pattern": FIELD_NAME_PATTERN,
                                },
                                "uniqueItems": True,
                            },
                        },
                        "required": ["properties", "required"],
                        "additionalProperties": False,
                    },
                    "x-section": {"type": "string", "pattern": SECTION_ID_PATTERN},
                },
                "required": ["if", "then", "x-section"],
                "additionalProperties": False,
            },
        },
        "properties": {
            "type": "object",
            "patternProperties": {
                FIELD_NAME_PATTERN: {
                    "anyOf": [
                        {"$ref": "#/$defs/attachmentFieldJSONSchema"},
                        {"$ref": "#/$defs/booleanFieldJSONSchema"},
                        {"$ref": "#/$defs/collectionFieldJSONSchema"},
                        {"$ref": "#/$defs/dateTimeFieldJSONSchema"},
                        {"$ref": "#/$defs/locationFieldJSONSchema"},
                        {"$ref": "#/$defs/multipleChoiceListFieldJSONSchema"},
                        {"$ref": "#/$defs/numericFieldJSONSchema"},
                        {"$ref": "#/$defs/singleChoiceListFieldJSONSchema"},
                        {"$ref": "#/$defs/textFieldJSONSchema"},
                    ]
                }
            },
            "additionalProperties": False,
        },
        "required": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": FIELD_NAME_PATTERN,
            },
            "uniqueItems": True,
        },
        "type": {"const": "object"},
        "unevaluatedProperties": {"const": False},
    },
    "required": ["$schema", "properties", "required", "type", "unevaluatedProperties"],
    "additionalProperties": False,
}


# Main

main_event_type_schema = {
    "$id": "https://earthranger.com/event_type_schema.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "Event Type V2 schema",
    "properties": {
        "json": json_field_schema,
        "ui": ui_schema,
        "auto-generate": {"type": "boolean"},
        "readonly": {"type": "boolean"},
        "icon_id": {"type": "string"},
        "image_url": {"type": "string"},
    },
    "required": ["json", "ui"],
    "$defs": {
        # Form element JSON subschemas
        "attachmentFieldJSONSchema": attachment_field_json_schema,
        "booleanFieldJSONSchema": boolean_field_json_schema,
        "collectionFieldJSONSchema": collection_field_json_schema,
        "dateTimeFieldJSONSchema": date_time_field_json_schema,
        "locationFieldJSONSchema": location_field_json_schema,
        "multipleChoiceListFieldJSONSchema": multiple_choice_list_field_json_schema,
        "numericFieldJSONSchema": numeric_field_json_schema,
        "singleChoiceListFieldJSONSchema": single_choice_list_field_json_schema,
        "textFieldJSONSchema": text_field_json_schema,
        # Condition JSON subschemas
        "containsConditionSchema": contains_condition_schema,
        "isEmptyConditionSchema": is_empty_condition_schema,
        "isNotEmptyConditionSchema": is_not_empty_condition_schema,
        "isExactlyConditionSchema": is_exactly_condition_schema,
        "isContainedByConditionSchema": is_contained_by_condition_schema,
        "isNotContainedByConditionSchema": is_not_contained_by_condition_schema,
        # Form element UI subschemas
        "attachmentFieldUISchema": attachment_field_ui_schema,
        "booleanFieldUISchema": boolean_field_ui_schema,
        "choiceListFieldUISchema": choice_list_field_ui_schema,
        "collectionFieldUISchema": collection_field_ui_schema,
        "dateTimeFieldUISchema": date_time_field_ui_schema,
        "headerUISchema": header_ui_schema,
        "locationFieldUISchema": location_field_ui_schema,
        "numericFieldUISchema": numeric_field_ui_schema,
        "sectionUISchema": section_ui_schema,
        "textFieldUISchema": text_field_ui_schema,
    },
    "additionalProperties": False,
}
