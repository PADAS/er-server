import jsonschema
from rest_framework import serializers

from activity.models import (
    PATROL_STATE_CHOICES,
    PRIORITY_CHOICES,
)
from activity.serializers import (
    EventFileSerializer,
    EventNoteSerializer,
    EventSourceSerializer
)


# TODO: move these to fields.py
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

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        try:
            jsonschema.validate(data, self.schema)
        except jsonschema.exceptions.ValidationError as ex:
            raise serializers.ValidationError(ex.message)
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
        priority_number = next(
            filter(
                lambda priority_choice: priority_choice[1] == value,
                self.choices
            )
        )[0]

        return priority_number

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
                lambda choice: choice[1] == value,
                self.choices
            )
        )[0]

        return priority_state

    def to_internal_value(self, data):
        self.validate(data)

        return data


# TODO: move these to base.py
class BaseSerializer(serializers.Serializer):
    """This serves as the base class from which all other serializers extend.

    It contains fields common to all API resources in the app.
    """

    id = serializers.CharField(read_only=True)


class TimestampMixin(serializers.Serializer):
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class PatrolSegmentSerializer(BaseSerializer):
    """Serializer class for a Patrol Segment"""

    # patrol = PatrolSerializer()
    patrol_type = serializers.CharField()
    priority = PriorityField()
    state = PatrolStateField()
    sources = EventSourceSerializer()
    scheduled_start = serializers.DateTimeField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    start_location = serializers.CoordinateField()
    icon_id = serializers.URLField()
    image_url = serializers.URLField()
    # reports = ReportSerializer(many=True)


class PatrolSerializer(BaseSerializer, TimestampMixin):
    """Serializer class for a Patrol"""

    files = EventFileSerializer(many=True)
    notes = EventNoteSerializer(many=True)
    patrol_segments = PatrolSegmentSerializer(many=True)
    priority = PriorityField()
    serial_number = serializers.IntegerField()
    state = PatrolStateField()
    title = serializers.CharField(allow_null=True)
