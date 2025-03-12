import json

from jsonschema import ValidationError, validate
from jsonschema.validators import Draft202012Validator

from rest_framework import serializers


class JSONSchemaField(serializers.Field):
    """
    Custom field to validate that the input is a valid JSON Schema.
    """

    def __init__(self, meta_schema=None, validate_sections=True, **kwargs):
        super().__init__(**kwargs)
        self.meta_schema = meta_schema
        self.validate_sections = validate_sections

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

            if self.validate_sections:
                self._validate_parent_references(data)

        except ValidationError as e:
            json_path = ".".join(str(s) for s in e.path)
            raise serializers.ValidationError(f"Invalid JSON Schema: {e.message} at {json_path}")

        return data

    def _validate_parent_references(self, data):
        def _check_section_exists(data, param, parent_key):
            ui = data.get("ui", {})
            sections = ui.get("sections", {})
            items = ui.get(param, {})
            errors = []

            for name, value in items.items():
                parent = value.get(parent_key)
                if parent not in sections:
                    errors.append(
                        f"'{name}' has an invalid 'parent' or 'section': '{parent}' does not exist in 'sections'."
                    )

            return errors

        """
        Validates that every 'section' in 'ui' references a valid key in 'sections'.
        """
        header_errors = _check_section_exists(data, "headers", "section")

        order_errors = [
            (
                f"{section} in 'order' does not exist in 'sections'"
                if section not in data.get("ui", {}).get("sections", {})
                else ""
            )
            for section in data.get("ui", {}).get("order", [])
        ]

        errors = header_errors + order_errors
        filtered_errors = [err for err in errors if err]

        if filtered_errors:
            raise serializers.ValidationError("Validation errors: " + " ".join(filtered_errors))
