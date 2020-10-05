import copy
from django.contrib.gis.geos.point import Point
from drf_extra_fields.geo_fields import PointField
from rest_framework import serializers, validators
from rest_framework.fields import DateTimeField
from collections import OrderedDict
import activity.models
import utils
from accounts.serializers import UserDisplaySerializer, get_user_display
from activity.models import PATROL_STATE_CHOICES, PC_OPEN, PRI_NONE, PRIORITY_CHOICES
from activity.models import Patrol, PatrolNote, PatrolSegment
from activity.serializers import AlertRuleSerializer, EventSourceSerializer
from activity.serializers import fields, ReportedByRelatedField
from activity.serializers.base import BaseSerializer, RevisionMixin, TimestampMixin
from activity.serializers.fields import choicefield_serializer, text_field
from utils.drf import PointValidator
priority_choices_serializer = choicefield_serializer(PRIORITY_CHOICES, default=PRI_NONE)
state_choices_serializer = choicefield_serializer(PATROL_STATE_CHOICES, default=PC_OPEN)

serializers_path = 'activity.serializers.patrol_serializers'


class PatrolFileSerializer(BaseSerializer, RevisionMixin):
    """Serializer class for a PatrolFile"""

    comment = serializers.CharField()
    created_by = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    ordernum = serializers.CharField()


class PatrolNoteSerializer(BaseSerializer, TimestampMixin, RevisionMixin):
    id = serializers.UUIDField(required=False, read_only=False)
    text = text_field()
    created_by_user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def create(self, validated_data):
        validated_data['patrol'] = self._kwargs.get('data').get('patrol')
        return activity.models.PatrolNote.objects.create(**validated_data)

    def to_representation(self, note):
        rep = super().to_representation(note)
        rep['updates'] = self.render_updates(note)
        return rep

    def render_updates(self, note):
        result = [
            dict(message='Note {action}'.format(
                action=self.get_action(revision),
                user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get('text', ''),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=self.get_patrol_update_type(revision, 'note'),
            )
            for revision in note.revision.all_user()
        ]
        return sorted(result, key=lambda u: u['time'], reverse=True)


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


class PatrolSegmentSerializer(BaseSerializer, RevisionMixin):
    id = serializers.UUIDField(required=False, read_only=False)
    patrol = PatrolList(required=False, read_only=True)
    patrol_type = PatrolTypeRelatedField(required=False)
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
        rep['updates'] = self.render_updates(instance)
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

    def render_updates(self, segment):
        revisions = list(iter(segment.revision.all_user().order_by('sequence')))
        result = [
            dict(
                message='{action}'.format(
                    action=self.get_action(revision),
                    user=get_user_display(revision.user)
                ),
                time=revision.revision_at.isoformat(),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=self.get_patrol_update_type(revision, 'segment'))
            for revision in revisions
        ]
        return sorted(result, key=lambda u: u['time'], reverse=True)


class PatrolSerializer(BaseSerializer, TimestampMixin, RevisionMixin):
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
        if self.context.get('include_updates', True):
            updates = self.render_updates(instance)
            for note in rep.get('notes', []):
                updates.extend(note['updates'])
            for f in rep.get('patrol_segments', []):
                updates.extend(f['updates'])
            rep['updates'] = sorted(updates, key=lambda u: u['time'], reverse=True)

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

    def update(self, instance, validated_data):

        patrol_id = instance.id
        patrol_notes = validated_data.get('notes', [])
        patrol_segments = validated_data.get('patrol_segments', [])

        self.create_update(patrol_id, patrol_notes, activity.models.PatrolNote)
        self.create_update(patrol_id, patrol_segments, activity.models.PatrolSegment)

        instance.priority = validated_data.get('priority', instance.priority)
        instance.state = validated_data.get('state', instance.state)
        instance.title = validated_data.get('title', instance.title)
        instance.objective = validated_data.get('objective', instance.objective)

        instance.save()
        return instance

    def create_update(self, patrol_id, validated_data, model):
        for data in validated_data:
            data['patrol_id'] = patrol_id
            data_id = data.get('id')
            if data_id:
                instance = model.objects.get(id=data_id)
                super().update(instance, data)
            else:
                model.objects.create(**data)

    def render_updates(self, patrol):
        revisions = list(iter(patrol.revision.all_user().order_by('sequence')))
        result = [
            dict(
                message='{action}'.format(
                    action=self.get_action(revision),
                    user=get_user_display(revision.user)
                ),
                time=revision.revision_at.isoformat(),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=self.get_patrol_update_type(revision)) for revision in revisions
        ]
        return result


class PatrolTemplateSerializer(BaseSerializer):
    title = serializers.CharField()
    recurrence_rules = serializers.CharField()
    patrol_type = serializers.CharField()
    length = serializers.CharField()
    alert_rule = AlertRuleSerializer()
    source = EventSourceSerializer()

