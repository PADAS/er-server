from rest_framework import serializers

from activity.serializers import (
    EventFileSerializer,
    EventNoteSerializer,
    EventSourceSerializer
)
from activity.serializers.base import BaseSerializer, TimestampMixin
from activity.serializers.fields import (
    CoordinateField,
    PatrolStateField,
    PriorityField,
)


class PatrolSerializer(BaseSerializer, TimestampMixin):
    """Serializer class for a Patrol"""

    files = EventFileSerializer(many=True)
    priority = PriorityField()
    serial_number = serializers.IntegerField()
    state = PatrolStateField()
    title = serializers.CharField(allow_null=True)


class PatrolNoteSerializer(BaseSerializer):
    text = serializers.CharField()
    created_by_user = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    patrol = PatrolSerializer(excludes=["notes"])


class PatrolSegmentSerializer(BaseSerializer):
    """Serializer class for a Patrol Segment"""

    patrol = PatrolSerializer(excludes=["patrol_segments"])
    patrol_type = serializers.CharField()
    priority = PriorityField()
    state = PatrolStateField()
    sources = EventSourceSerializer()
    scheduled_start = serializers.DateTimeField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    start_location = CoordinateField()
    icon_id = serializers.URLField()
    image_url = serializers.URLField()
    # reports = ReportSerializer(many=True)


PatrolSerializer.notes = PatrolNoteSerializer(many=True)
PatrolSerializer.patrol_segments = PatrolSegmentSerializer(
    excludes=["patrol"],
    many=True
)
