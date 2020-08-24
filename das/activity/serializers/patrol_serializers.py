from rest_framework import serializers

from activity.serializers import AlertRuleSerializer, EventSourceSerializer
from activity.serializers.base import (
    BaseSerializer,
    RevisionMixin,
    TimestampMixin,
)
from activity.serializers.fields import (
    CoordinateField,
    PatrolStateField,
    PriorityField,
)


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
    priority = PriorityField()
    serial_number = serializers.IntegerField()
    state = PatrolStateField()
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
    # priority = PriorityField()
    state = PatrolStateField()
    # sources = EventSourceSerializer()
    scheduled_start = serializers.DateTimeField()
    # start_time = serializers.DateTimeField()
    # end_time = serializers.DateTimeField()
    start_location = CoordinateField()
    end_location = CoordinateField()
    # icon_id = serializers.URLField()
    # image_url = serializers.URLField()
    # reports = ReportSerializer(many=True)


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
    default_priority = PriorityField()
    is_active = serializers.BooleanField()
