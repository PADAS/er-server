import jsonschema


class Conditions:

    def __init__(self, conditions):
        self.conditions = conditions

    def validate(self):
        jsonschema.validate(self.conditions, self.json_schema)

    json_schema = {
        "definitions": {
            "string_condition": {
                "type": "object",
                "title": "String condition",
                "properties": {
                    "name": {
                        "type": "string",
                    },
                    "operator": {
                        "type": "string",
                        "enum": ["contains"]
                    },
                    "value": {
                        "type": "string"
                    }
                }
            }
        },
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://earthranger.com/conditions.json",
        "type": "object",
        "title": "Business Rules Conditions Schema",
        "additionalProperties": False,
        "properties": {
            "all": {
                "$id": "#/properties/all",
                "type": "array",
                "title": "Array of conditions definitions",
                "minItems": 1,
                "items": {
                    "type": "object"
                }
            },
            "anyOf": {
                "$id": "#/properties/anyOf",
                "type": "array",
                "title": "Array of conditions definitions",
                "minItems": 1,
                "items": {
                    "type": "object"
                }
            },
        }
    }
