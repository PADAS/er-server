import json

from jsonschema import ValidationError
from jsonschema.validators import Draft202012Validator

from rest_framework import serializers

VALID_DRAFT = "https://json-schema.org/draft/2020-12/schema"


class JSONSchemaField(serializers.Field):
    """
    Custom field to validate that the input is a valid JSON Schema, using always
    the Draft202012Validator.
    """

    def __init__(self, meta_schema=None, validate_sections=False, **kwargs):
        super().__init__(**kwargs)
        self.meta_schema = meta_schema
        self.validate_sections = validate_sections

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if isinstance(data, bytes):
            try:
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
            # Validate draft version
            self._validate_draft_version(data)
            # Validate against meta schema
            Draft202012Validator(self.meta_schema).validate(data)

            if self.validate_sections:
                self._validate_parent_references(data)

        except ValidationError as e:
            json_path = ".".join(str(s) for s in e.path)
            raise serializers.ValidationError(f"Invalid JSON Schema: {e.message} at {json_path}")

        return json.dumps(data, indent=2)

    @staticmethod
    def _validate_parent_references(data):
        """
        Validates that every 'section' in 'ui' references a valid key in 'sections'.
        """

        def check_section_exists(data, param, parent_key):
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

        header_errors = check_section_exists(data, "headers", "section")

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

    def _validate_draft_version(self, data):
        # Only validate draft if 'json' key exists, otherwise let the main validator handle the missing key.
        if "json" in data:
            json_schema = data.get("json", {})
            schema_uri = json_schema.get("$schema")
            if schema_uri != VALID_DRAFT:
                raise serializers.ValidationError(f"$schema must be {VALID_DRAFT}")
