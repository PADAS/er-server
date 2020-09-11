from drf_extra_fields.geo_fields import PointField
from rest_framework import serializers, validators
from rest_framework.fields import DateTimeField
from collections import OrderedDict

import activity.models
import utils
from activity.models import PATROL_STATE_CHOICES, PC_ACTIVE, PRI_NONE, PRIORITY_CHOICES
from activity.models import Patrol
from activity.serializers import PatrolTypeSerializer, AlertRuleSerializer, EventSourceSerializer
from activity.serializers import fields, ReportedByRelatedField
from activity.serializers.base import BaseSerializer, RevisionMixin, TimestampMixin
from activity.serializers.fields import choicefield_serializer, text_field, SerializerMethodField
from observations.serializers import SourceSerializer
from utils.drf import PointValidator
priority_choices_serializer = choicefield_serializer(PRIORITY_CHOICES, default=PRI_NONE)
state_choices_serializer = choicefield_serializer(PATROL_STATE_CHOICES, default=PC_ACTIVE)

serializers_path = 'activity.serializers.patrol_serializers'

class PatrolFileSerializer(BaseSerializer, RevisionMixin):
    """Serializer class for a PatrolFile"""

    comment = serializers.CharField()
    created_by = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    ordernum = serializers.CharField()


class PatrolNoteSerializer(BaseSerializer, RevisionMixin):
    text = text_field()
    created_by_user = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )

class PatrolSerializer(BaseSerializer, TimestampMixin):
    """Serializer class for a Patrol"""

    objective = text_field(required=False, allow_blank=True)
    priority = priority_choices_serializer
    serial_number = serializers.IntegerField(
        allow_null=True, required=False,
        validators=[validators.UniqueValidator(queryset=Patrol.objects.all())]
    )
    state = state_choices_serializer
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    time_range = fields.DateTimeRangeField(required=False)

    files = PatrolFileSerializer(many=True, required=False, read_only=True)
    notes = PatrolNoteSerializer(many=True, required=False, read_only=True)
    patrol_segments = SerializerMethodField(
        method_name='get_patrol_segments', many=True, excludes=["patrol"],
        serializer=f'{serializers_path}.PatrolSegmentSerializer')

    def create(self, validated_data):
        return Patrol.objects.create(**validated_data)

    def get_patrol_segments(self, obj):
        return [
            PatrolSegmentSerializer(instance=x, excludes=["patrol"]).data
            for x in obj.patrol_segments.all()
        ]


class LeaderRelatedField(ReportedByRelatedField):
    def get_object_queryset(self):
        for p in activity.models.PROVENANCE_CHOICES:
            provenance = p[0]
            values = list(
                activity.models.PatrolSegment.objects.get_leader_for_provenance(provenance))
            if values:
                yield provenance, values


class PatrolTypeRelatedField(serializers.RelatedField):

    def get_queryset(self):
        return activity.models.PatrolType.objects.all_sort()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            try:
                return activity.models.PatrolType.objects.get_by_value(data)
            except activity.models.EventType.DoesNotExist:
                raise serializers.ValidationError(f'patrol_type: {data} does not exist')

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display)
                            for row in self.get_queryset()))


class PatrolSegmentSerializer(BaseSerializer):
    patrol = PatrolSerializer(required=False, excludes=['patrol_segments', 'files', 'notes', 'serial_number',
                                                        'updates', 'objective', 'created_at', 'updated_at'])
    patrol_type = PatrolTypeRelatedField(required=False)
    state = state_choices_serializer
    leader = LeaderRelatedField(required=False, allow_null=True)
    scheduled_start = DateTimeField(required=False)
    time_range = fields.DateTimeRangeField(required=False)
    start_location = PointField(required=False, allow_null=True,
                                validators=[PointValidator()])
    end_location = PointField(required=False, allow_null=True,
                              validators=[PointValidator()])

    @staticmethod
    def resolve_image_url(patrolsegment):
        return patrolsegment.patrol_type.image_url if patrolsegment.patrol_type else None

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        if request:
            image_url = self.resolve_image_url(instance)
            rep['image_url'] = utils.add_base_url(request, image_url)
        rep['patrol_type'] = str(instance.patrol_type.id) if instance.patrol_type else None
        return rep

    def create(self, validated_data):
        patrol = validated_data.get('patrol')

        if patrol:
            patrol_o = Patrol.objects.create(**patrol)
            validated_data['patrol_id'] = patrol_o.id
            validated_data.pop('patrol')

        return activity.models.PatrolSegment.objects.create(**validated_data)


class PatrolTemplateSerializer(BaseSerializer):
    title = serializers.CharField()
    recurrence_rules = serializers.CharField()
    patrol_type = serializers.CharField()
    length = serializers.CharField()
    alert_rule = AlertRuleSerializer()
    source = EventSourceSerializer()

