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

    objective = serializers.CharField(allow_blank=True)
    priority = priority_field()
    serial_number = serializers.IntegerField(allow_null=True, required=False)
    state = patrol_state_field()
    title = serializers.CharField(allow_blank=True, max_length=255)

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
    patrol_type = serializers.CharField(
        allow_blank=True, allow_null=True, required=False
    )
    priority = priority_field()
    state = patrol_state_field()
    source = SourceSerializer(many=True, required=False)
    scheduled_start = serializers.DateTimeField(allow_null=True, required=False)
    time_range = DateTimeRangeField(allow_null=True, required=False)
    start_location = CoordinateField(allow_null=True, required=False)
    end_location = CoordinateField(allow_null=True, required=False)
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
    value = serializers.CharField(max_length=50)
    display = serializers.CharField(max_length=255)
    ordernum = serializers.CharField(
        allow_blank=True, allow_null=True, required=False
    )
    icon = serializers.CharField(max_length=100, allow_blank=True)
    default_priority = priority_field()
    is_active = serializers.BooleanField(default=True)
