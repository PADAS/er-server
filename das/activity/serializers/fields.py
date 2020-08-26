import jsonschema
from rest_framework import serializers

from activity.models import (
    PATROL_STATE_CHOICES,
    PC_ACTIVE,
    PRI_NONE,
    PRIORITY_CHOICES,
)


class CoordinateField(serializers.Field):
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


def patrol_state_field(*args, **kwargs):
    return serializers.ChoiceField(
        choices=PATROL_STATE_CHOICES,
        default=PC_ACTIVE,
        *args,
        **kwargs
    )


def priority_field(*args, **kwargs):
    return serializers.ChoiceField(
        choices=PRIORITY_CHOICES,
        default=PRI_NONE,
        *args,
        **kwargs
    )
