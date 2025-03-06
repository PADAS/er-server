import json

from jsonschema import ValidationError, validate
from jsonschema.validators import Draft202012Validator

from rest_framework import serializers


class JSONSchemaField(serializers.Field):
    """
    Custom field to validate that the input is a valid JSON Schema.
    """

    def __init__(self, meta_schema=None, **kwargs):
        super().__init__(**kwargs)
        self.meta_schema = meta_schema

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if isinstance(data, bytes):
            try:
                # Decode bytes to string and parse as JSON
                data = data.decode("utf-8")
                data = json.loads(data)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise serializers.ValidationError(f"Invalid JSON data: {str(e)}")

        elif isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                raise serializers.ValidationError(f"Invalid JSON string: {str(e)}")

        elif not isinstance(data, dict):
            raise serializers.ValidationError("The schema must be a JSON object.")

        try:
            Draft202012Validator.check_schema(data)
            validate(instance=data, schema=self.meta_schema)

        except ValidationError as e:
            raise serializers.ValidationError(f"Invalid JSON Schema: {e.message}")

        return data
