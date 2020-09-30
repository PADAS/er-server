import copy
from django.contrib.gis.geos.point import Point
from drf_extra_fields.geo_fields import PointField
from rest_framework import serializers, validators
from rest_framework.fields import DateTimeField
from collections import OrderedDict
import activity.models
import utils
from activity.models import PATROL_STATE_CHOICES, PC_ACTIVE, PRI_NONE, PRIORITY_CHOICES
from activity.models import Patrol, PatrolNote, PatrolSegment
from activity.serializers import AlertRuleSerializer, EventSourceSerializer
from activity.serializers import fields, ReportedByRelatedField
from activity.serializers.base import BaseSerializer, RevisionMixin, TimestampMixin
from activity.serializers.fields import choicefield_serializer, text_field
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


class PatrolNoteSerializer(BaseSerializer, TimestampMixin):
    id = serializers.UUIDField(required=False, read_only=False)
    text = text_field()
    created_by_user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def create(self, validated_data):
        validated_data['patrol'] = self._kwargs.get('data').get('patrol')
        return activity.models.PatrolNote.objects.create(**validated_data)


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
            data = data if isinstance(data, str) else data.value
            try:
                return activity.models.PatrolType.objects.get_by_value(data)
            except activity.models.PatrolType.DoesNotExist:
                raise serializers.ValidationError(f'patrol_type: {data} does not exist')

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display)
                            for row in self.get_queryset()))


class PatrolList(serializers.Serializer):
    pass


class PatrolSegmentSerializer(BaseSerializer):
    id = serializers.UUIDField(required=False, read_only=False)
    patrol = PatrolList(required=False, read_only=True)
    patrol_type = PatrolTypeRelatedField(required=False)
    state = state_choices_serializer
    leader = LeaderRelatedField(required=False, allow_null=True)
    scheduled_start = DateTimeField(required=False, allow_null=True)
    time_range = fields.DateTimeRangeField(required=False, allow_null=True)
    start_location = PointField(required=False, allow_null=True,
                                validators=[PointValidator()])
    end_location = PointField(required=False, allow_null=True,
                              validators=[PointValidator()])
    image_url = serializers.CharField(read_only=True, required=False)
    icon_id = serializers.CharField(read_only=True, required=False)

    @staticmethod
    def resolve_image_url(patrolsegment):
        return patrolsegment.patrol_type.image_url if patrolsegment.patrol_type else None

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        if request:
            image_url = self.resolve_image_url(instance)
            rep['image_url'] = utils.add_base_url(request, image_url)

        if rep.get('time_range') is None:
            rep['time_range'] = self.empty_timerange()

        rep['patrol_type'] = str(instance.patrol_type.value) if instance.patrol_type else None
        rep['icon_id'] = str(instance.patrol_type.icon_id) if instance.patrol_type else None
        rep['patrol'] = self.get_patrol(instance.patrol) if instance.patrol else None
        return rep

    def get_patrol(self, patrol):
        return PatrolSerializer(
            instance=patrol,
            includes=['id', 'patrol_type', 'priority', 'state', 'title']).data

    @staticmethod
    def empty_timerange():
        return {"start_time": None, "end_time": None}

    def create(self, validated_data):
        validated_data['patrol'] = self._kwargs.get('data').get('patrol')
        return activity.models.PatrolSegment.objects.create(**validated_data)

    def to_internal_value(self, data):
        data_updated = copy.copy(data)
        for field_name in ('end_location', 'start_location'):
            if field_name in data and isinstance(data[field_name], Point):
                data_updated[field_name] = {'latitude': data[field_name].y, 'longitude': data[field_name].x}

        return super().to_internal_value(data_updated)


class PatrolSerializer(BaseSerializer, TimestampMixin):
    """Serializer class for a Patrol"""

    objective = text_field(required=False, allow_blank=True, allow_null=True)
    priority = priority_choices_serializer
    serial_number = serializers.IntegerField(read_only=True)
    state = state_choices_serializer
    title = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    files = PatrolFileSerializer(many=True, required=False, read_only=True)
    notes = PatrolNoteSerializer(many=True, required=False)
    patrol_segments = PatrolSegmentSerializer(many=True, required=False, excludes=['patrol'])

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        for seg in rep.get('patrol_segments', []):
            seg.pop('patrol', 0)
        return rep

    def create(self, validated_data):
        patrol_notes = validated_data.pop('notes', [])
        patrol_segments = validated_data.pop('patrol_segments', [])
        new_patrol = Patrol.objects.create(**validated_data)
        for note in patrol_notes:
            note = copy.deepcopy(note)
            note['patrol_id'] = new_patrol.id
            PatrolNote.objects.create(**note)

        for segment in patrol_segments:
            segment = copy.deepcopy(segment)
            segment['patrol_id'] = new_patrol.id
            PatrolSegment.objects.create(**segment)

        return Patrol.objects.get(id=new_patrol.id)

    def _ser_create(self, instance, update_items, items_serializer, item_model):
        for item in update_items:
            update_item = copy.deepcopy(item)
            update_item['patrol'] = instance
            update_item_id = update_item.pop('id', None)
            serializer = items_serializer(data=update_item, context=self.context)
            serializer.is_valid(raise_exception=True)

            if update_item_id:
                item_instance = item_model.objects.get(id=update_item_id)
                serializer.update(item_instance, update_item)
            else:
                serializer.create(update_item)

    def update(self, instance, validated_data):
        update_fields = []
        for k, v in validated_data.items():
            if k == 'notes':
                self._ser_create(instance, v, PatrolNoteSerializer, activity.models.PatrolNote)
                continue
            if k == 'patrol_segments':
                self._ser_create(instance, v, PatrolSegmentSerializer, activity.models.PatrolSegment)
                continue
            if getattr(instance, k) != v:
                setattr(instance, k, v)
                if k not in ('id',):
                    update_fields.append(k)
        if update_fields:
            instance.save()
        return instance



class PatrolTemplateSerializer(BaseSerializer):
    title = serializers.CharField()
    recurrence_rules = serializers.CharField()
    patrol_type = serializers.CharField()
    length = serializers.CharField()
    alert_rule = AlertRuleSerializer()
    source = EventSourceSerializer()

