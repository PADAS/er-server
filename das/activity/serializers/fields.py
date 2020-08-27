import jsonschema
from rest_framework import serializers

from activity.models import (
    PATROL_STATE_CHOICES,
    PC_ACTIVE,
    PRI_NONE,
    PRIORITY_CHOICES,
)


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


def patrol_state_field(**kwargs):
    choices = kwargs.pop('choices', PATROL_STATE_CHOICES)
    default = kwargs.pop('default', PC_ACTIVE)

    return serializers.ChoiceField(
        choices=choices,
        default=default,
        **kwargs
    )


def priority_field(**kwargs):
    choices = kwargs.pop('choices', PRIORITY_CHOICES)
    default = kwargs.pop('default', PRI_NONE)

    return serializers.ChoiceField(
        choices=choices,
        default=default,
        **kwargs
    )


def text_field(**kwargs):
    style = kwargs.pop('style', {'base_template': 'textarea.html'})

    return serializers.CharField(
        style=style,
        **kwargs
    )
