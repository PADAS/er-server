import jsonschema
from rest_framework import serializers
from rest_framework.fields import empty


class CoordinateField(serializers.Field):
    allow_null = True
    schema = {
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number"
            },
            "longitude": {
                "type": "number"
            }
        }
    }

    @classmethod
    def validate(cls, data):
        try:
            jsonschema.validate(instance=data, schema=cls.schema)
        except jsonschema.exceptions.ValidationError as ex:
            raise serializers.ValidationError(ex.message)

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        self.validate(data)

        return data


def choicefield_serializer(choices, default=empty, **kwargs):
    return serializers.ChoiceField(choices=choices, default=default, **kwargs)


def text_field(**kwargs):
    style = kwargs.pop('style', {'base_template': 'textarea.html'})
    return serializers.CharField(style=style, **kwargs)
