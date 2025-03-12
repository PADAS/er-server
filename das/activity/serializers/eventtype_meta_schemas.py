text_field_schema = {
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
        "type": {"type": "string", "const": "string"},
        "additionalProperties": False,
    },
    "required": ["deprecated", "format"],
}

location_field_schema = {
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
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
        "additionalProperties": False,
    },
    "required": ["deprecated", "description", "title", "type", "properties"],
}

numeric_field_schema = {
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
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
        "type": {"type": "string", "const": "array"},
        "items": {
            "type": "object",
            "properties": {
                "anyOf": choice_any_of_schema,
                "type": {"type": "string"},
            },
            "additionalItems": False,
        },
        "additionalProperties": False,
        "uniqueItems": True,
    },
    "required": ["deprecated", "description", "title", "type", "items"],
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
    },
}

ui_text_schema = {
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
        "parent": {"type": "string", "pattern": "^section-[A-Za-z0-9]"},
        "type": {"const": "CHOICE_LIST"},
        "additionalProperties": False,
    },
    "required": ["parent", "type"],
}

ui_date_time_schema = {
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
    "$schema": "http://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "type": "object",
    "title": "UI Sections schema for EventType Builder",
    "properties": {
        "columns": {"type": "number", "enum": [1, 2]},
        "isActive": {"type": "boolean"},
        "label": {"type": "string"},
        "leftColumn": ui_section_columns,
        "rightColumn": ui_section_columns,
        "parent": {"type": "string", "pattern": "^section-[A-Za-z0-9]"},
        "type": {"const": "SECTIONS"},
        "additionalProperties": False,
    },
    "required": ["columns", "isActive", "label", "leftColumn", "rightColumn"],
}

ui_schema = {
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
                "^header-[A-Za-z0-9]": {"$ref": "#/$defs/uiHeadersSchema"},
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
                "^section-[A-Za-z0-9]": {"$ref": "#/$defs/uiSectionsSchema"},
            },
        },
    },
    "required": ["fields", "headers", "order", "sections"],
}


json_field_schema = {
    "$schema": "http://json-schema.org/draft/2020-12/schema",
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
