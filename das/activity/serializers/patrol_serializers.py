from rest_framework import serializers
from drf_extra_fields.fields import DateTimeRangeField

from activity.serializers import AlertRuleSerializer, EventSourceSerializer
from activity.serializers.base import (
    BaseSerializer,
    RevisionMixin,
    TimestampMixin,
)
from activity.serializers.fields import (
    CoordinateField,
    patrol_state_field,
    priority_field,
)
from observations.serializers import SourceSerializer


class PatrolFileSerializer(BaseSerializer, RevisionMixin):
    """Serializer class for a PatrolFile"""

    comment = serializers.CharField()
    created_by = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    ordernum = serializers.CharField()


class PatrolSerializer(BaseSerializer, TimestampMixin):
    """Serializer class for a Patrol"""

    objective = serializers.CharField()
    priority = priority_field()
    serial_number = serializers.IntegerField()
    state = patrol_state_field()
    title = serializers.CharField(allow_null=True)

    files = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()
    patrol_segments = serializers.SerializerMethodField()

    def get_files(self, obj):
        return [
            PatrolFileSerializer(instance=x, excludes=["patrol"]).data
            for x in obj.files.all()
        ]

    def get_notes(self, obj):
        return [
            PatrolNoteSerializer(instance=x, excludes=["patrol"]).data
            for x in obj.notes.all()
        ]

    def get_patrol_segments(self, obj):
        return [
            PatrolSegmentSerializer(instance=x, excludes=["patrol"]).data
            for x in obj.patrol_assignments.all()
        ]


class PatrolNoteSerializer(BaseSerializer, RevisionMixin):
    text = serializers.CharField()
    created_by_user = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    patrol = PatrolSerializer(excludes=["notes"])


class PatrolSegmentSerializer(BaseSerializer):
    """Serializer class for a Patrol Segment"""

    patrol = PatrolSerializer(excludes=['patrol_segments'])
    patrol_type = serializers.CharField()
    priority = priority_field()
    state = patrol_state_field()
    source = SourceSerializer(many=True)
    scheduled_start = serializers.DateTimeField()
    time_range = DateTimeRangeField()
    start_location = CoordinateField()
    end_location = CoordinateField()
    icon_id = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    # reports = ReportSerializer(many=True)

    def get_icon_id(self, obj):
        return obj.icon_id

    def get_image_url(self, obj):
        return obj.image_url


class PatrolTemplateSerializer(BaseSerializer):
    title = serializers.CharField()
    recurrence_rules = serializers.CharField()
    patrol_type = serializers.CharField()
    length = serializers.CharField()
    alert_rule = AlertRuleSerializer()
    source = EventSourceSerializer()


class PatrolTypeSerializer(BaseSerializer):
    value = serializers.CharField()
    display = serializers.CharField()
    ordernum = serializers.CharField()
    icon = serializers.CharField()
    default_priority = priority_field()
    is_active = serializers.BooleanField()
