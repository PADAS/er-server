import jsonschema

from django.core.exceptions import ValidationError
from rest_framework.serializers import Field


class CoordinateField(Field):
    allow_null = True
    schema = {
        "type": "object",
        "properties": {"latitude": {"type": "number"}, "longitude": {"type": "number"}},
    }

    @classmethod
    def validate(cls, data):
        try:
            jsonschema.validate(instance=data, schema=cls.schema)
        except jsonschema.exceptions.ValidationError as error:
            raise ValidationError(error.message)

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        self.validate(data)

        return data
