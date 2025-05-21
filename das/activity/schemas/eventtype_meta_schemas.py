text_field_schema = {
    "type": "object",
    "title": "Text schema for EventType Builder",
    "properties": {
        "default": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "type": {"const": "string"},
    },
    "additionalProperties": False,
    "required": ["deprecated", "description", "title", "type"],
}

attachment_field_schema = {
    "type": "object",
    "title": "Attachment field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "format": {"const": "uri"},
        "title": {"type": "string"},
        "type": {"const": "string"},
    },
    "required": ["deprecated", "title", "type", "format"],
    "additionalProperties": False,
}


date_time_field_schema = {
    "type": "object",
    "title": "Date Time field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "format": {"type": "string", "enum": ["date-time", "date", "time"]},
        "default": {"type": "string"},
        "title": {"type": "string"},
        "type": {"type": "string", "const": "string"},
    },
    "required": ["deprecated", "format"],
    "additionalProperties": False,
}

location_field_schema = {
    "type": "object",
    "title": "Location field schema for EventType Builder",
    "properties": {
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "type": {"type": "string", "const": "object"},
        "properties": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "const": "number"},
                        "minimum": {"type": "number", "const": -90},
                        "maximum": {"type": "number", "const": 90},
                    },
                    "additionalProperties": False,
                },
                "longitude": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "const": "number"},
                        "minimum": {"type": "number", "const": -180},
                        "maximum": {"type": "number", "const": 180},
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["latitude", "longitude"],
            "additionalProperties": False,
        },
    },
    "required": ["deprecated", "description", "title", "type", "properties"],
    "additionalProperties": False,
}

numeric_field_schema = {
    "type": "object",
    "title": "Numeric field schema for EventType Builder",
    "properties": {
        "default": {"type": "number"},
        "deprecated": {"type": "boolean"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "type": {"type": "string", "const": "number"},
        "maximum": {"type": "number"},
        "minimum": {"type": "number"},
    },
    "required": ["deprecated", "description", "title", "type"],
    "additionalProperties": False,
}

reference_choice_object_schema_in_anyOf = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"$ref": {"type": "string", "format": "uri"}},
        "required": ["$ref"],
    },
    "minItems": 1,
}

choice_field_schema = {
    "type": "object",
    "title": "Choice field schema for EventType Builder",
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "anyOf": reference_choice_object_schema_in_anyOf,
    },
    "required": ["deprecated", "description", "title", "type", "anyOf"],
    "additionalProperties": False,
}

choice_list_field_schema = {
    "type": "object",
    "title": "Choice list field schema for EventType Builder",
    "properties": {
        "type": {"type": "string", "const": "array"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "deprecated": {"type": "boolean"},
        "items": {
            "type": "object",
            "properties": {
                "anyOf": reference_choice_object_schema_in_anyOf,
                "type": {"type": "string"},
            },
            "additionalItems": False,
        },
        "uniqueItems": {"type": "boolean"},
    },
    "required": ["deprecated", "description", "title", "type", "items"],
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
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "additionalProperties": {"type": "boolean", "const": False},
                "type": {"type": "string", "const": "object"},
                "required": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                "properties": {
                    "type": "object",
                    "patternProperties": {
                        ".*": {
                            "anyOf": [
                                {"$ref": "#/$defs/textField"},
                                {"$ref": "#/$defs/numericField"},
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
            },
        },
        "title": {"type": "string"},
        "type": {"type": "string", "const": "array"},
        "unevaluatedItems": {"type": "boolean", "const": False},
        "maxItems": {"type": "integer"},
        "minItems": {"type": "integer"},
        "additionalProperties": False,
    },
    "$defs": {
        "textField": text_field_schema,
        "numericField": numeric_field_schema,
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

ui_text_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Text schema for EventType Builder",
    "properties": {
        "inputType": {"type": "string", "enum": ["SHORT_TEXT", "LONG_TEXT"]},
        "parent": {"type": "string"},
        "placeholder": {"type": "string"},
        "type": {"const": "TEXT"},
        "additionalProperties": False,
    },
    "required": ["inputType", "parent", "placeholder", "type"],
}

ui_attachment_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Attachment schema for EventType Builder",
    "properties": {
        "allowableFileTypes": {
            "type": "array",
            "items": {"type": "string", "enum": ["video", "document", "audio", "image"]},
        },
        "parent": {"type": "string"},
        "type": {"const": "ATTACHMENT"},
        "additionalProperties": False,
    },
    "required": ["allowableFileTypes", "parent", "type"],
}

ui_collection_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Collection schema for EventType Builder",
    "properties": {
        "buttonText": {"type": "string"},
        "columns": {"type": "number", "enum": [1, 2]},
        "itemIdentifier": {"type": "string"},
        "itemName": {"type": "string"},
        "leftColumn": {"type": "array", "items": {"type": "string"}},
        "rightColumn": {"type": "array", "items": {"type": "string"}},
        "parent": {"type": "string"},
        "type": {"const": "COLLECTION"},
        "additionalProperties": False,
    },
    "required": ["parent", "type"],
}

ui_choice_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Choice List schema for EventType Builder",
    "properties": {
        "choices": {
            "type": "object",
            "properties": {
                "eventTypeCategories": {"type": "array", "items": {"type": "string", "format": "uuid"}},
                "existingChoiceList": {"type": "array", "items": {"type": "string", "format": "uuid"}},
                "featureCategories": {"type": "array", "items": {"type": "string", "format": "uuid"}},
                "subjectGroups": {"type": "array", "items": {"type": "string", "format": "uuid"}},
                "subjectSubtypes": {"type": "array", "items": {"type": "string", "format": "uuid"}},
                "myDataType": {
                    "type": "string",
                    "enum": [
                        "SUBJECTS_FROM_SUBJECT_SUBTYPE",
                        "SUBJECTS_FROM_SUBJECT_GROUP",
                        "FEATURES_FROM_FEATURE_GROUP",
                        "EVENT_TYPES_FROM_EVENT_CATEGORY",
                        "",
                    ],
                },
                "type": {"type": "string", "enum": ["EXISTING_CHOICE_LIST", "MY_DATA", "CHOICE_LIST"]},
            },
            "additionalProperties": False,
        },
        "inputType": {"type": "string", "enum": ["DROPDOWN", "LIST"]},
        "placeholder": {"type": "string"},
        "parent": {"type": "string"},
        "type": {"const": "CHOICE_LIST"},
        "additionalProperties": False,
    },
    "required": ["parent", "type"],
}

ui_date_time_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Date Time schema for EventType Builder",
    "properties": {
        "parent": {"type": "string"},
        "type": {"const": "DATE_TIME"},
        "additionalProperties": False,
    },
    "required": ["parent", "type"],
}

ui_location_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Location schema for EventType Builder",
    "properties": {
        "parent": {"type": "string"},
        "type": {"const": "LOCATION"},
        "additionalProperties": False,
    },
    "required": ["parent", "type"],
}

ui_numeric_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Numeric schema for EventType Builder",
    "properties": {
        "placeholder": {"type": "string"},
        "parent": {"type": "string"},
        "type": {"const": "NUMERIC"},
        "additionalProperties": False,
    },
    "required": ["parent", "type", "placeholder"],
}

ui_headers_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Headers schema for EventType Builder",
    "properties": {
        "label": {"type": "string"},
        "section": {"type": "string"},
        "size": {"type": "string", "enum": ["SMALL", "MEDIUM", "LARGE"]},
        "additionalProperties": False,
    },
    "required": ["label", "section", "size"],
}

ui_section_columns = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"name": {"type": "string"}, "type": {"type": "string", "enum": ["field", "header"]}},
        "additionalProperties": False,
    },
}

ui_sections_schema = {
    "additionalProperties": False,
    "type": "object",
    "title": "UI Sections schema for EventType Builder",
    "properties": {
        "columns": {"type": "number", "enum": [1, 2]},
        "isActive": {"type": "boolean"},
        "label": {"type": "string"},
        "leftColumn": ui_section_columns,
        "rightColumn": ui_section_columns,
        "parent": {"type": "string"},
        "type": {"const": "SECTIONS"},
        "additionalProperties": False,
    },
    "required": ["columns", "isActive", "label", "leftColumn", "rightColumn"],
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
            "items": {"type": "string"},
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
        "$schema": {"type": "string", "const": "https://json-schema.org/draft/2020-12/schema"},
        "additionalProperties": {"type": "boolean", "const": False},
        "properties": {
            "type": "object",
            "additionalProperties": False,
            "patternProperties": {
                ".*": {
                    "anyOf": [
                        {"$ref": "#/$defs/textField"},
                        {"$ref": "#/$defs/numericField"},
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
        "type": {"type": "string", "const": "object"},
    },
    "required": ["$schema", "properties"],
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
    },
    "required": ["json", "ui"],
    "$defs": {
        "textField": text_field_schema,
        "numericField": numeric_field_schema,
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
        "uiHeadersSchema": ui_headers_schema,
        "uiSectionsSchema": ui_sections_schema,
    },
}
