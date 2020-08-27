from rest_framework import serializers, validators
from drf_extra_fields.fields import DateTimeRangeField

from activity.models import Patrol
from activity.serializers import AlertRuleSerializer, EventSourceSerializer
from activity.serializers.base import (BaseSerializer, RevisionMixin,
                                       TimestampMixin)
from activity.serializers.fields import (CoordinateField, patrol_state_field,
                                         priority_field, text_field)
from observations.serializers import SourceSerializer


class PatrolFileSerializer(BaseSerializer, RevisionMixin):
    """Serializer class for a PatrolFile"""

    comment = serializers.CharField()
    created_by = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    ordernum = serializers.CharField()


class PatrolSerializer(BaseSerializer, RevisionMixin, TimestampMixin):
    """Serializer class for a Patrol"""

    objective = text_field(allow_blank=True)
    priority = priority_field()
    serial_number = serializers.IntegerField(
        allow_null=True, required=False,
        validators=[validators.UniqueValidator(queryset=Patrol.objects.all())]
    )
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
    text = text_field()
    created_by_user = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    patrol = PatrolSerializer(excludes=["notes"])


class PatrolSegmentSerializer(BaseSerializer):
    """Serializer class for a Patrol Segment"""

    patrol = PatrolSerializer(
        excludes=['patrol_segments', 'files', 'notes', 'serial_number', 'state',
                  'updates', 'objective', 'created_at', 'updated_at']
    )
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
    # reports = ReportSerializer(many=True)

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        patrol_type = getattr(instance, 'patrol_type', None)

        if patrol_type is not None:
            ret['icon_id'] = patrol_type.icon_id
            ret['image_url'] = patrol_type.marker_icon(patrol_type.icon)
            ret['priority'] = patrol_type.default_priority
            ret['patrol_type'] = str(patrol_type.id)

        return ret


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
