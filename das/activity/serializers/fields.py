import jsonschema
from rest_framework import serializers

from activity.models import (
    PATROL_STATE_CHOICES,
    PRIORITY_CHOICES,
)

"""Re-invented ChoiceFields

ChoiceFields work neatly with ModelSerializers, but because we could do with 
some finely-grained controls in `to_representation` and `to_internal_value` 
(especially for PriorityField), we are well-and-truly better off working with 
vanilla Field and vanilla Serializer.
"""


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


class PriorityField(serializers.Field):
    """This field represents Priority levels"""

    choices = PRIORITY_CHOICES
    priority_choices_numbers = list(
        map(
            lambda priority_choice: priority_choice[0],
            choices
        )
    )

    @classmethod
    def validate(cls, data):
        is_data_valid = data in cls.priority_choices_numbers

        if not is_data_valid:
            raise serializers.ValidationError(
                f'Value must be one of {cls.priority_choices_numbers}'
            )

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        """Validate the 'data' sent by the client is valid, return the 'data'"""
        self.validate(data)

        return data


class PatrolStateField(serializers.Field):
    """This field represents Patrol State levels"""

    choices = PATROL_STATE_CHOICES

    @classmethod
    def validate(cls, data):
        is_data_valid = data in cls.choices

        if not is_data_valid:
            raise serializers.ValidationError(
                f'Value must be one of {cls.choices}'
            )

    def to_representation(self, value):
        priority_state = next(
            filter(
                lambda choice: choice[1] == value or choice[0] == value,
                self.choices
            )
        )[0]

        return priority_state

    def to_internal_value(self, data):
        self.validate(data)

        return data
