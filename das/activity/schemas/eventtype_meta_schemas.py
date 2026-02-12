text_field_schema = {
    "type": "object",
    "title": "Text field schema for EventType Builder",
    "properties": {
        "default": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "string"},
    },
    "additionalProperties": False,
    "required": ["deprecated", "title", "type"],
}

attachment_field_schema = {
    "type": "object",
    "title": "Attachment field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "format": {"const": "uri"},
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "string"},
    },
    "required": ["deprecated", "format", "title", "type"],
    "additionalProperties": False,
}


date_time_field_schema = {
    "type": "object",
    "title": "Date Time field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "format": {"enum": ["date-time", "date", "time"]},
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "string"},
    },
    "required": ["deprecated", "format", "title", "type"],
    "additionalProperties": False,
}

location_field_schema = {
    "type": "object",
    "title": "Location field schema for EventType Builder",
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
        "required": {"const": ["latitude", "longitude"]},
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "object"},
        "unevaluatedProperties": {"const": False},
    },
    "required": ["deprecated", "properties", "required", "title", "type", "unevaluatedProperties"],
    "additionalProperties": False,
}

numeric_field_schema = {
    "type": "object",
    "title": "Numeric field schema for EventType Builder",
    "properties": {
        "default": {"type": "number"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "maximum": {"type": "number"},
        "minimum": {"type": "number"},
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "number"},
    },
    "required": ["deprecated", "title", "type"],
    "additionalProperties": False,
}

boolean_field_schema = {
    "type": "object",
    "title": "Boolean field schema for EventType Builder",
    "properties": {
        "default": {"type": "boolean"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "boolean"},
    },
    "required": ["deprecated", "title", "type"],
    "additionalProperties": False,
}

reference_choice_object_schema_in_anyOf = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "$ref": {"type": "string", "format": "uri"},
        },
        "required": ["$ref"],
    },
    "minItems": 1,
}

choice_field_schema = {
    "type": "object",
    "title": "Choice field schema for EventType Builder",
    "properties": {
        "anyOf": reference_choice_object_schema_in_anyOf,
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "string"},
    },
    "required": ["anyOf", "deprecated", "title", "type"],
    "additionalProperties": False,
}

choice_list_field_schema = {
    "type": "object",
    "title": "Choice list field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "items": {
            "type": "object",
            "properties": {
                "anyOf": reference_choice_object_schema_in_anyOf,
                "type": {"const": "string"},
            },
            "required": ["anyOf", "type"],
            "additionalItems": False,
        },
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "array"},
        "uniqueItems": {"const": True},
    },
    "required": ["deprecated", "items", "title", "type", "uniqueItems"],
    "additionalProperties": False,
}


# Base definition for a choice object *after* rendering/reference resolution
# Allows required const/title, optional description, and any other custom properties (like x-icon)
rendered_choice_item_schema = {
    "type": "object",
    "title": "Rendered Choice Item Schema",
    "properties": {
        "const": {"type": ["string", "number", "boolean"]},
        "title": {"type": "string"},
        "description": {"type": "string"},
        # Allow any other properties, typically starting with x-
    },
    "required": ["const", "title"],
    "additionalProperties": True,  # Allow x-* and other potential fields
}

rendered_choice_reference_schema_in_anyOf = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "oneOf": {"type": "array", "items": rendered_choice_item_schema},
    },
    "required": ["type", "title", "oneOf"],
}

# Meta-schema for a choice field *after* rendering
rendered_choice_field_schema = {
    "type": "object",
    "title": "Rendered Choice Field Meta-Schema",
    "properties": {
        "type": {"type": ["string", "number", "boolean"]},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "default": {"type": "string"},
        "anyOf": {
            "type": "array",
            "items": rendered_choice_reference_schema_in_anyOf,
            "minItems": 1,
        },
    },
    "required": ["type", "title", "description", "deprecated", "anyOf"],
    "additionalProperties": False,
}


rendered_choice_list_field_schema = {
    "title": "Rendered Multiple Choice Field Meta-Schema",
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "array"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "uniqueItems": {"type": "boolean"},
        "default": {"type": "array", "items": {"type": "string"}},
        "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "anyOf": {"type": "array", "items": rendered_choice_reference_schema_in_anyOf, "minItems": 1},
            },
            "required": ["anyOf"],
            "additionalProperties": False,
        },
    },
    "required": ["type", "title", "description", "deprecated", "items"],
    "additionalProperties": False,
}


collection_field_schema = {
    "$id": "https://earthranger.com/collection_field.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Collection field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "items": {
            "type": "object",
            "properties": {
                "additionalProperties": {"const": False},
                "properties": {
                    "type": "object",
                    "patternProperties": {
                        ".*": {
                            "anyOf": [
                                {"$ref": "#/$defs/textField"},
                                {"$ref": "#/$defs/numericField"},
                                {"$ref": "#/$defs/booleanField"},
                                {"$ref": "#/$defs/attachmentField"},
                                {"$dynamicRef": "#collectionField"},  # self reference
                                {"$ref": "#/$defs/dateTimeField"},
                                {"$ref": "#/$defs/locationField"},
                                {"$ref": "#/$defs/choiceField"},
                                {"$ref": "#/$defs/choiceListField"},
                                {"$ref": "#/$defs/renderedChoiceField"},
                                {"$ref": "#/$defs/renderedChoiceListField"},
                            ]
                        }
                    },
                },
                "required": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": {"const": True},
                },
                "type": {"const": "object"},
                "unevaluatedProperties": {"const": False},
            },
            "required": ["properties", "required", "type"],
            "oneOf": [
                {"required": ["additionalProperties"]},
                {"required": ["unevaluatedProperties"]},
            ],
        },
        "maxItems": {"type": "integer"},
        "minItems": {"type": "integer"},
        "title": {"type": "string", "maxLength": 140},
        "type": {"const": "array"},
        "unevaluatedItems": {"const": False},
    },
    "$defs": {
        "textField": text_field_schema,
        "numericField": numeric_field_schema,
        "booleanField": boolean_field_schema,
        "attachmentField": attachment_field_schema,
        "collectionField": {
            "$dynamicAnchor": "collectionField",
            "$ref": "#",  # Reference the root collection field schema
        },
        "dateTimeField": date_time_field_schema,
        "locationField": location_field_schema,
        "choiceField": choice_field_schema,
        "choiceListField": choice_list_field_schema,
        "renderedChoiceField": rendered_choice_field_schema,
        "renderedChoiceListField": rendered_choice_list_field_schema,
    },
}

conditional_dependents_schema = {
    "type": "array",
    "items": {"type": "string", "pattern": "^section-.*"},
    "uniqueItems": {"const": True},
}

ui_text_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Text schema for EventType Builder",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "inputType": {"enum": ["SHORT_TEXT", "LONG_TEXT"]},
        "parent": {"type": "string"},
        "placeholder": {"type": "string"},
        "type": {"const": "TEXT"},
    },
    "required": ["inputType", "parent", "type"],
}

ui_attachment_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Attachment schema for EventType Builder",
    "properties": {
        "allowableFileTypes": {
            "type": "array",
            "items": {"enum": ["video", "document", "audio", "image"]},
        },
        "conditionalDependents": conditional_dependents_schema,
        "parent": {"type": "string"},
        "type": {"const": "ATTACHMENT"},
    },
    "required": ["allowableFileTypes", "parent", "type"],
}

ui_collection_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Collection schema for EventType Builder",
    "properties": {
        "buttonText": {"type": "string"},
        "columns": {"enum": [1, 2]},
        "conditionalDependents": conditional_dependents_schema,
        "itemIdentifier": {"type": "string"},
        "itemName": {"type": "string"},
        "leftColumn": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": {"const": True},
        },
        "parent": {"type": "string"},
        "rightColumn": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": {"const": True},
        },
        "type": {"const": "COLLECTION"},
    },
    "required": ["columns", "itemName", "leftColumn", "parent", "rightColumn", "type"],
}

ui_choice_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Choice List schema for EventType Builder",
    "properties": {
        "choices": {
            "type": "object",
            "properties": {
                "eventTypeCategories": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "existingChoiceList": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "featureCategories": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "subjectGroups": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "subjectSubtypes": {
                    "type": "array",
                    "items": {"type": "string", "format": "uuid"},
                },
                "myDataType": {
                    "enum": [
                        "",
                        "EVENT_TYPES_FROM_EVENT_CATEGORY",
                        "FEATURES_FROM_FEATURE_CATEGORY",
                        "SOURCES",
                        "SUBJECTS_FROM_SUBJECT_GROUP",
                        "SUBJECTS_FROM_SUBJECT_SUBTYPE",
                        "USERS",
                    ],
                },
                "type": {"enum": ["EXISTING_CHOICE_LIST", "MY_DATA"]},
            },
            "additionalProperties": False,
        },
        "conditionalDependents": conditional_dependents_schema,
        "inputType": {"enum": ["DROPDOWN", "LIST"]},
        "placeholder": {"type": "string"},
        "parent": {"type": "string"},
        "type": {"const": "CHOICE_LIST"},
    },
    "required": ["choices", "inputType", "parent", "type"],
}

ui_date_time_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Date Time schema for EventType Builder",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "parent": {"type": "string"},
        "type": {"const": "DATE_TIME"},
    },
    "required": ["parent", "type"],
}

ui_location_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Location schema for EventType Builder",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "parent": {"type": "string"},
        "type": {"const": "LOCATION"},
    },
    "required": ["parent", "type"],
}

ui_numeric_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Numeric schema for EventType Builder",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "placeholder": {"type": "string"},
        "parent": {"type": "string"},
        "type": {"const": "NUMERIC"},
    },
    "required": ["parent", "type"],
}

ui_boolean_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Boolean schema for EventType Builder",
    "properties": {
        "conditionalDependents": conditional_dependents_schema,
        "parent": {"type": "string"},
        "type": {"const": "BOOLEAN"},
    },
    "required": ["parent", "type"],
}

ui_headers_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Headers schema for EventType Builder",
    "properties": {
        "label": {"type": "string"},
        "section": {"type": "string", "pattern": "^section-.*"},
        "size": {"enum": ["SMALL", "MEDIUM", "LARGE"]},
    },
    "required": ["label", "section", "size"],
}

ui_section_columns = {
    "type": "array",
    "items": {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"const": "field"},
                },
                "required": ["name", "type"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "pattern": "^header-.*"},
                    "type": {"const": "header"},
                },
                "required": ["name", "type"],
                "additionalProperties": False,
            },
        ],
    },
}

ui_sections_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Sections schema for EventType Builder",
    "properties": {
        "columns": {"enum": [1, 2]},
        "conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "id": {"type": "string", "pattern": "^condition-.*"},
                    "operator": {
                        "enum": [
                            "CONTAINS",
                            "IS_EXACTLY",
                            "IS_EMPTY",
                            "IS_NOT_EMPTY",
                            "IS_CONTAINED_BY",
                            "IS_NOT_CONTAINED_BY",
                        ]
                    },
                    "value": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "null"},
                            {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        ]
                    },
                },
                "required": ["field", "id", "operator"],
                "additionalProperties": False,
            },
        },
        "isActive": {"type": "boolean"},
        "label": {"type": "string"},
        "leftColumn": ui_section_columns,
        "rightColumn": ui_section_columns,
    },
    "required": ["columns", "isActive", "leftColumn", "rightColumn"],
}

contains_condition_schema = {
    "type": "object",
    "title": "Contains condition schema for EventType Builder",
    "properties": {
        "properties": {
            "type": "object",
            "patternProperties": {
                ".*": {
                    "type": "object",
                    "properties": {
                        "anyOf": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
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
                                        },
                                        "type": {"const": "array"},
                                    },
                                    "required": ["allOf", "type"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "required": {"type": "array", "items": {"type": "string"}},
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
                                }
                            ],
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
            "items": {"type": "string"},
            "maxItems": 1,
            "minItems": 1,
        },
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}

is_empty_condition_schema = {
    "type": "object",
    "title": "Is Empty condition schema for EventType Builder",
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
                                "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1}
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
                            "minProperties": 1,
                            "maxProperties": 1,
                            "patternProperties": {
                                ".*": {
                                    "type": "object",
                                    "properties": {"type": {"const": "array"}, "maxItems": {"const": 0}},
                                    "required": ["type", "maxItems"],
                                    "additionalProperties": False,
                                }
                            },
                            "additionalProperties": False,
                        },
                        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
                    },
                    "required": ["properties", "required"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "properties": {
                            "type": "object",
                            "minProperties": 1,
                            "maxProperties": 1,
                            "patternProperties": {
                                ".*": {
                                    "type": "object",
                                    "properties": {"type": {"const": "null"}},
                                    "required": ["type"],
                                    "additionalProperties": False,
                                }
                            },
                            "additionalProperties": False,
                        },
                        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
                    },
                    "required": ["properties", "required"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "properties": {
                            "type": "object",
                            "minProperties": 1,
                            "maxProperties": 1,
                            "patternProperties": {
                                ".*": {
                                    "type": "object",
                                    "properties": {"type": {"const": "object"}, "maxProperties": {"const": 0}},
                                    "required": ["type", "maxProperties"],
                                    "additionalProperties": False,
                                }
                            },
                            "additionalProperties": False,
                        },
                        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
                    },
                    "required": ["properties", "required"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "properties": {
                            "type": "object",
                            "minProperties": 1,
                            "maxProperties": 1,
                            "patternProperties": {
                                ".*": {
                                    "type": "object",
                                    "properties": {"type": {"const": "string"}, "maxLength": {"const": 0}},
                                    "required": ["type", "maxLength"],
                                    "additionalProperties": False,
                                }
                            },
                            "additionalProperties": False,
                        },
                        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
                    },
                    "required": ["properties", "required"],
                    "additionalProperties": False,
                },
            ],
            "items": False,
        }
    },
    "required": ["anyOf"],
    "additionalProperties": False,
}

is_not_empty_condition_schema = {
    "type": "object",
    "title": "Is Not Empty condition schema for EventType Builder",
    "properties": {
        "properties": {
            "type": "object",
            "minProperties": 1,
            "maxProperties": 1,
            "patternProperties": {
                ".*": {
                    "type": "object",
                    "properties": {
                        "allOf": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
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
                                            "minItems": 5,
                                            "maxItems": 5,
                                            "prefixItems": [
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "type": {"const": "array"},
                                                        "minItems": {"const": 1},
                                                    },
                                                    "required": ["type", "minItems"],
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
                                                        "type": {"const": "object"},
                                                        "minProperties": {"const": 1},
                                                    },
                                                    "required": ["type", "minProperties"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "type": {"const": "string"},
                                                        "minLength": {"const": 1},
                                                    },
                                                    "required": ["type", "minLength"],
                                                    "additionalProperties": False,
                                                },
                                            ],
                                            "items": False,
                                        }
                                    },
                                    "required": ["anyOf"],
                                    "additionalProperties": False,
                                },
                            ],
                            "items": False,
                        }
                    },
                    "required": ["allOf"],
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        },
        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}

is_exactly_condition_schema = {
    "type": "object",
    "title": "Is Exactly condition schema for EventType Builder",
    "properties": {
        "properties": {
            "type": "object",
            "minProperties": 1,
            "maxProperties": 1,
            "patternProperties": {
                ".*": {
                    "type": "object",
                    "properties": {
                        "anyOf": {
                            "type": "array",
                            "minItems": 5,
                            "maxItems": 5,
                            "prefixItems": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "array"},
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
                                        },
                                        "maxItems": {"type": "number"},
                                    },
                                    "required": ["type", "allOf", "maxItems"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "boolean"},
                                        "const": {"type": ["boolean", "null"]},
                                    },
                                    "required": ["type", "const"],
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
                                        "type": {"const": "object"},
                                        "properties": {
                                            "type": "object",
                                            "additionalProperties": {"type": "object", "maxProperties": 0},
                                        },
                                        "required": {"type": "array", "items": {"type": "string"}},
                                        "unevaluatedProperties": {"const": False},
                                    },
                                    "required": ["type", "properties", "required", "unevaluatedProperties"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {"const": {"type": ["string", "null"]}, "type": {"const": "string"}},
                                    "required": ["const", "type"],
                                    "additionalProperties": False,
                                },
                            ],
                            "items": False,
                        }
                    },
                    "required": ["anyOf"],
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        },
        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}

is_contained_by_condition_schema = {
    "type": "object",
    "title": "Is Contained By condition schema for EventType Builder",
    "properties": {
        "properties": {
            "type": "object",
            "minProperties": 1,
            "maxProperties": 1,
            "patternProperties": {
                ".*": {
                    "type": "object",
                    "properties": {
                        "anyOf": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
                            "prefixItems": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "array"},
                                        "minItems": {"const": 1},
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "enum": {"type": "array", "items": {"type": "string"}}
                                            },
                                            "required": ["enum"],
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["type", "minItems", "items"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "object"},
                                        "minProperties": {"const": 1},
                                        "propertyNames": {
                                            "type": "object",
                                            "properties": {
                                                "enum": {"type": "array", "items": {"type": "string"}}
                                            },
                                            "required": ["enum"],
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["type", "minProperties", "propertyNames"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "string"},
                                        "enum": {"type": "array", "items": {"type": "string"}},
                                    },
                                    "required": ["type", "enum"],
                                    "additionalProperties": False,
                                },
                            ],
                            "items": False,
                        }
                    },
                    "required": ["anyOf"],
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        },
        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}

is_not_contained_by_condition_schema = {
    "type": "object",
    "title": "Is Not Contained By condition schema for EventType Builder",
    "properties": {
        "properties": {
            "type": "object",
            "minProperties": 1,
            "maxProperties": 1,
            "patternProperties": {
                ".*": {
                    "type": "object",
                    "properties": {
                        "anyOf": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
                            "prefixItems": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "allOf": {
                                            "type": "array",
                                            "minItems": 2,
                                            "maxItems": 2,
                                            "prefixItems": [
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "type": {"const": "array"},
                                                        "minItems": {"const": 1},
                                                    },
                                                    "required": ["type", "minItems"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "not": {
                                                            "type": "object",
                                                            "properties": {
                                                                "type": {"const": "array"},
                                                                "items": {
                                                                    "type": "object",
                                                                    "properties": {
                                                                        "enum": {
                                                                            "type": "array",
                                                                            "items": {"type": "string"}
                                                                        }
                                                                    },
                                                                    "required": ["enum"],
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["type", "items"],
                                                            "additionalProperties": False,
                                                        }
                                                    },
                                                    "required": ["not"],
                                                    "additionalProperties": False,
                                                },
                                            ],
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
                                            "minItems": 2,
                                            "maxItems": 2,
                                            "prefixItems": [
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "type": {"const": "object"},
                                                        "minProperties": {"const": 1},
                                                    },
                                                    "required": ["type", "minProperties"],
                                                    "additionalProperties": False,
                                                },
                                                {
                                                    "type": "object",
                                                    "properties": {
                                                        "not": {
                                                            "type": "object",
                                                            "properties": {
                                                                "type": {"const": "object"},
                                                                "propertyNames": {
                                                                    "type": "object",
                                                                    "properties": {
                                                                        "enum": {
                                                                            "type": "array",
                                                                            "items": {"type": "string"}
                                                                        }
                                                                    },
                                                                    "required": ["enum"],
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["type", "propertyNames"],
                                                            "additionalProperties": False,
                                                        }
                                                    },
                                                    "required": ["not"],
                                                    "additionalProperties": False,
                                                },
                                            ],
                                            "items": False,
                                        }
                                    },
                                    "required": ["allOf"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "string"},
                                        "not": {
                                            "type": "object",
                                            "properties": {
                                                "enum": {"type": "array", "items": {"type": "string"}}
                                            },
                                            "required": ["enum"],
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["type", "not"],
                                    "additionalProperties": False,
                                },
                            ],
                            "items": False,
                        }
                    },
                    "required": ["anyOf"],
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        },
        "required": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 1},
    },
    "required": ["properties", "required"],
    "additionalProperties": False,
}

ui_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI schema for EventTypeV2 Builder",
    "properties": {
        "fields": {
            "type": "object",
            "additionalProperties": False,
            "patternProperties": {
                ".*": {
                    "oneOf": [
                        {"$ref": "#/$defs/uiTextSchema"},
                        {"$ref": "#/$defs/uiNumericSchema"},
                        {"$ref": "#/$defs/uiBooleanSchema"},
                        {"$ref": "#/$defs/uiAttachmentSchema"},
                        {"$ref": "#/$defs/uiCollectionSchema"},
                        {"$ref": "#/$defs/uiDateTimeSchema"},
                        {"$ref": "#/$defs/uiLocationSchema"},
                        {"$ref": "#/$defs/uiChoiceSchema"},
                    ]
                }
            },
        },
        "headers": {
            "type": "object",
            "additionalProperties": False,
            "patternProperties": {
                "^header-.*": {"$ref": "#/$defs/uiHeadersSchema"},
            },
        },
        "order": {
            "type": "array",
            "items": {"type": "string", "pattern": "^section-.*"},
            "uniqueItems": True,
        },
        "sections": {
            "type": "object",
            "additionalProperties": False,
            "patternProperties": {
                "^section-.*": {"$ref": "#/$defs/uiSectionsSchema"},
            },
        },
    },
    "required": ["fields", "headers", "order", "sections"],
}


json_field_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "Json schema for EventTypeV2 Builder",
    "properties": {
        "$schema": {"const": "https://json-schema.org/draft/2020-12/schema"},
        "additionalProperties": {"const": False},
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
                                        {"$ref": "#/$defs/containsCondition"},
                                        {"$ref": "#/$defs/isExactlyCondition"},
                                        {"$ref": "#/$defs/isEmptyCondition"},
                                        {"$ref": "#/$defs/isNotEmptyCondition"},
                                        {"$ref": "#/$defs/isContainedByCondition"},
                                        {"$ref": "#/$defs/isNotContainedByCondition"},
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
                                "additionalProperties": False,
                                "patternProperties": {
                                    ".*": {
                                        "anyOf": [
                                            {"$ref": "#/$defs/textField"},
                                            {"$ref": "#/$defs/numericField"},
                                            {"$ref": "#/$defs/booleanField"},
                                            {"$ref": "#/$defs/attachmentField"},
                                            {"$ref": "#/$defs/collectionField"},
                                            {"$ref": "#/$defs/dateTimeField"},
                                            {"$ref": "#/$defs/locationField"},
                                            {"$ref": "#/$defs/choiceField"},
                                            {"$ref": "#/$defs/choiceListField"},
                                            {"$ref": "#/$defs/renderedChoiceField"},
                                            {"$ref": "#/$defs/renderedChoiceListField"},
                                        ]
                                    }
                                },
                            },
                            "required": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                        },
                        "required": ["properties", "required"],
                        "additionalProperties": False,
                    },
                    "x-section": {"type": "string"},
                },
                "required": ["if", "then", "x-section"],
                "additionalProperties": False,
            },
        },
        "properties": {
            "type": "object",
            "additionalProperties": False,
            "patternProperties": {
                ".*": {
                    "anyOf": [
                        {"$ref": "#/$defs/textField"},
                        {"$ref": "#/$defs/numericField"},
                        {"$ref": "#/$defs/booleanField"},
                        {"$ref": "#/$defs/attachmentField"},
                        {"$ref": "#/$defs/collectionField"},
                        {"$ref": "#/$defs/dateTimeField"},
                        {"$ref": "#/$defs/locationField"},
                        {"$ref": "#/$defs/choiceField"},
                        {"$ref": "#/$defs/choiceListField"},
                        {"$ref": "#/$defs/renderedChoiceField"},
                        {"$ref": "#/$defs/renderedChoiceListField"},
                    ]
                }
            },
        },
        "required": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "type": {"const": "object"},
        "unevaluatedProperties": {"const": False},
    },
    "required": ["$schema", "properties", "required", "type"],
    "oneOf": [
        {"required": ["additionalProperties"]},
        {"required": ["unevaluatedProperties"]},
    ],
}


main_event_type_schema = {
    "$id": "https://earthranger.com/event_type_schema.json",
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "Event Type V2 schema for EventType Builder",
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
        "textField": text_field_schema,
        "numericField": numeric_field_schema,
        "booleanField": boolean_field_schema,
        "attachmentField": attachment_field_schema,
        "collectionField": collection_field_schema,
        "dateTimeField": date_time_field_schema,
        "locationField": location_field_schema,
        "choiceField": choice_field_schema,
        "choiceListField": choice_list_field_schema,
        "renderedChoiceField": rendered_choice_field_schema,
        "renderedChoiceListField": rendered_choice_list_field_schema,
        "uiTextSchema": ui_text_schema,
        "uiAttachmentSchema": ui_attachment_schema,
        "uiCollectionSchema": ui_collection_schema,
        "uiChoiceSchema": ui_choice_schema,
        "uiDateTimeSchema": ui_date_time_schema,
        "uiLocationSchema": ui_location_schema,
        "uiNumericSchema": ui_numeric_schema,
        "uiBooleanSchema": ui_boolean_schema,
        "uiHeadersSchema": ui_headers_schema,
        "uiSectionsSchema": ui_sections_schema,
        "containsCondition": contains_condition_schema,
        "isExactlyCondition": is_exactly_condition_schema,
        "isEmptyCondition": is_empty_condition_schema,
        "isNotEmptyCondition": is_not_empty_condition_schema,
        "isContainedByCondition": is_contained_by_condition_schema,
        "isNotContainedByCondition": is_not_contained_by_condition_schema,
    },
}
