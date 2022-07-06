import copy
import datetime
import json
from collections import OrderedDict

import pytz

from django.contrib.contenttypes.models import ContentType
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.fields import DateTimeField

import activity.models
import usercontent.serializers
import utils
from accounts.serializers import UserDisplaySerializer, get_user_display
from activity.models import (PATROL_STATE_CHOICES, PC_CANCELLED, PC_DONE,
                             PC_OPEN, PRI_NONE, PRIORITY_CHOICES, Patrol,
                             PatrolNote, PatrolSegment)
from activity.serializers import (AlertRuleSerializer, EventSourceSerializer,
                                  PatrolSegmentEventSerializer, fields)
from activity.serializers.base import FileSerializerMixin, RevisionMixin
from core.fields import GEOPointField, choicefield_serializer, text_field
from core.serializers import (BaseSerializer, GenericRelatedField,
                              PointValidator, TimestampMixin)
from revision.manager import AC_ADDED, AC_RELATION_DELETED, AC_UPDATED

priority_choices_serializer = choicefield_serializer(
    PRIORITY_CHOICES, default=PRI_NONE)
state_choices_serializer = choicefield_serializer(
    PATROL_STATE_CHOICES, default=PC_OPEN)

serializers_path = 'activity.serializers.patrol_serializers'


class PatrolList(serializers.Serializer):
    pass


class PatrolFileSerializer(FileSerializerMixin, BaseSerializer, RevisionMixin):
    """Serializer class for a PatrolFile"""
    usercontent_id = serializers.UUIDField(required=False)
    usercontent_type = serializers.PrimaryKeyRelatedField(
        required=False, queryset=ContentType.objects.all())

    usercontent = usercontent.serializers.UserContentSerializer(required=False)

    created_by = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )

    comment = serializers.CharField(
        allow_blank=True, required=False,)
    ordernum = serializers.IntegerField(required=False, allow_null=True)

    def create(self, validated_data):
        validated_data['patrol'] = self._kwargs.get('data').get('patrol')
        validated_data = self.pre_create(validated_data)
        return activity.models.PatrolFile.objects.create(**validated_data)

    @property
    def parent_name(self):
        return "patrol"

    def get_instance_parent_id(self, instance):
        return instance.patrol.id

    def get_update_type(self, revision):
        return self.get_patrol_update_type(revision)


class PatrolNoteSerializer(BaseSerializer, TimestampMixin, RevisionMixin):
    id = serializers.UUIDField(required=False, read_only=False)
    text = text_field()
    created_by_user = serializers.HiddenField(
        default=serializers.CurrentUserDefault())

    def create(self, validated_data):
        validated_data['patrol'] = self._kwargs.get('data').get('patrol')
        return activity.models.PatrolNote.objects.create(**validated_data)

    def to_representation(self, note):
        rep = super().to_representation(note)
        rep['updates'] = self.render_updates(note)
        return rep

    def render_updates(self, note):
        def get_action(revision):
            if revision.action == AC_UPDATED:
                field_mapping = {'text': 'Note Text'}
                fieldnames = [field_mapping[k] for k in revision.data.keys() if
                              k in field_mapping]
                return '{0} fields: {1}'.format(revision.get_action_display(),
                                                ', '.join(fieldnames))

            return revision.get_action_display()
        result = [
            dict(message='Note {action}'.format(
                action=get_action(revision),
                user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get('text', ''),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=self.get_patrol_update_type(revision, 'note'),
            )
            for revision in note.revision.all_user()
        ]
        return sorted(result, key=lambda u: u['time'], reverse=True)


class LeaderRelatedField(GenericRelatedField):
    def get_field_mapping(self, label="Leader"):
        return super().get_field_mapping(label)

    def get_object_queryset(self):
        request = self.context.get('request')
        for p in activity.models.PROVENANCE_CHOICES:
            provenance = p[0]
            values = list(
                activity.models.PatrolSegment.objects.get_leader_for_provenance(provenance, request.user))
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
                raise serializers.ValidationError(
                    f'patrol_type: {data} does not exist')

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display)
                            for row in self.get_queryset()))


class PatrolRelatedField(serializers.RelatedField):
    queryset = activity.models.Patrol.objects.all()

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                return activity.models.PatrolType.objects.get_by_value(data)
            except activity.models.PatrolType.DoesNotExist:
                raise serializers.ValidationError(
                    f'patrol_type: {data} does not exist')


class PatrolSegmentSerializer(BaseSerializer, RevisionMixin):
    id = serializers.UUIDField(required=False, read_only=False)
    patrol = serializers.PrimaryKeyRelatedField(required=True, read_only=False,
                                                queryset=Patrol.objects.all())
    patrol_type = PatrolTypeRelatedField(required=False)
    leader = LeaderRelatedField(required=False, allow_null=True)
    scheduled_start = DateTimeField(required=False, allow_null=True)
    scheduled_end = DateTimeField(required=False, allow_null=True)
    time_range = fields.DateTimeRangeField(required=False, allow_null=True)
    start_location = GEOPointField(
        required=False, allow_null=True, validators=[PointValidator()])
    end_location = GEOPointField(
        required=False, allow_null=True, validators=[PointValidator()])
    image_url = serializers.CharField(read_only=True, required=False)
    icon_id = serializers.CharField(read_only=True, required=False)
    events = PatrolSegmentEventSerializer(many=True, read_only=True, context={
        'include_related_events': True})

    def to_internal_value(self, data):
        sch_start = data.get('scheduled_start')
        sch_end = data.get('scheduled_end')

        if sch_start and sch_end and sch_start > sch_end:
            raise serializers.ValidationError(
                'scheduled_start time has to be earlier than scheduled_end time')
        return super().to_internal_value(data)

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

        rep['patrol_type'] = str(
            instance.patrol_type.value) if instance.patrol_type else None
        rep['icon_id'] = str(
            instance.patrol_type.icon_id) if instance.patrol_type else None
        rep['updates'] = self.render_updates(instance)
        return rep

    @staticmethod
    def empty_timerange():
        return {"start_time": None, "end_time": None}

    def create(self, validated_data):
        return activity.models.PatrolSegment.objects.create(**validated_data)

    def render_updates(self, segment):
        last_scheduled_end = None

        def action(revision, fmapping):
            nonlocal last_scheduled_end
            revision_time = revision.revision_at
            scheduled_end = revision.data.get(
                'scheduled_end', last_scheduled_end)
            if revision.action == AC_UPDATED:
                fieldnames = []
                for k, v in revision.data.items():
                    if k == 'time_range' and v:
                        values = json.loads(v)
                        if values.get('lower'):
                            fieldnames.append('Start Time')
                        if values.get('upper'):
                            upper = parse_datetime(values.get('upper'))
                            fieldnames.append(
                                'End Time' if scheduled_end or revision_time > upper else "Auto-End Time")
                    elif k in field_mapping:
                        fieldnames.append(field_mapping.get(k))
                return '{0} fields: {1}'.format(revision.get_action_display(), ', '.join(fieldnames))
            return self.get_action(revision, fmapping)

        revisions = list(
            iter(segment.revision.all_user().order_by('sequence')))
        field_mapping = {'scheduled_start': 'Scheduled Start',
                         'scheduled_end': 'Scheduled End',
                         'leader_id': 'Tracking Subject',
                         'start_location': 'Start Location',
                         'end_location': 'End Location',
                         'time_range': 'Patrol Time'
                         }

        result = [
            dict(
                message='{action}'.format(
                    action=action(revision, field_mapping),
                    user=get_user_display(revision.user)
                ),
                time=revision.revision_at.isoformat(),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=self.get_patrol_update_type(revision, 'segment'))
            for revision in revisions if (revision.action == AC_RELATION_DELETED) or
                                         (revision.action == AC_UPDATED
                                          and set(field_mapping.keys()) & set(revision.data.keys()))
        ]

        event_results = self.render_event_updates(segment.events.all())
        result.extend(event_results)

        return sorted(result, key=lambda u: u['time'], reverse=True)

    def render_event_updates(self, events):
        results = []

        def get_action(revision, e):
            if revision.action == AC_ADDED:
                verbose_name = 'Incident Collection' if e.event_type.is_collection else 'Report'
                return f'{verbose_name} {revision.get_action_display()}'

        for event in events:
            revisions = list(
                iter(event.revision.all_user().order_by('sequence')))
            result = [
                dict(
                    message='{action}'.format(
                        action=get_action(revision, event)),
                    time=revision.revision_at.isoformat(),
                    user=UserDisplaySerializer().to_representation(revision.user),
                    type=self.get_patrol_update_type(revision, 'event'))
                for revision in revisions if (revision.action == AC_ADDED)
            ]
            results.extend(result)

            if event.out_relationships.exists():
                for o in event.out_relationships.all():
                    revisions = list(
                        iter(o.to_event.revision.all_user().order_by('sequence')))
                    updates = [
                        dict(
                            message='Report Added',
                            time=revision.revision_at.isoformat(),
                            user=UserDisplaySerializer().to_representation(revision.user),
                            type=self.get_patrol_update_type(revision, 'event'))
                        for revision in revisions if (revision.action == AC_ADDED)
                    ]
                    results.extend(updates)

        return results


class TrackedBySerializer(serializers.Serializer):
    leader = LeaderRelatedField(read_only=True)


class PatrolSerializer(BaseSerializer, TimestampMixin, RevisionMixin):
    """Serializer class for a Patrol"""

    objective = text_field(required=False, allow_blank=True, allow_null=True)
    priority = priority_choices_serializer
    serial_number = serializers.IntegerField(read_only=True)
    state = state_choices_serializer
    title = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255)
    files = PatrolFileSerializer(many=True, required=False, read_only=True)
    notes = PatrolNoteSerializer(many=True, required=False)
    patrol_segments = PatrolSegmentSerializer(
        many=True, required=False, excludes=['patrol'])

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        for seg in rep.get('patrol_segments', []):
            seg.pop('patrol', 0)
        if self.context.get('include_updates', True):
            updates = self.render_updates(instance)
            # for note in rep.get('notes', []):
            #     updates.extend(note['updates'])
            # for f in rep.get('patrol_segments', []):
            #     updates.extend(f['updates'])
            rep['updates'] = sorted(
                updates, key=lambda u: u['time'], reverse=True)

        return rep

    def validate(self, attrs):
        if attrs.get("state"):
            attrs["state"] = self._update_patrol_state(attrs)
        return super().validate(attrs)

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
        self.create_update(patrol_id, patrol_segments,
                           activity.models.PatrolSegment)

        instance.priority = validated_data.get('priority', instance.priority)
        instance.state = validated_data.get('state', instance.state)
        instance.title = validated_data.get('title', instance.title)
        instance.objective = validated_data.get(
            'objective', instance.objective)

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
        verbose_name = patrol._meta.verbose_name.title()
        field_mapping = {'state': 'State is {}', 'title': 'Title'}
        last_state = None

        def get_user(revision):
            nonlocal last_state
            state = revision.data.get('state', last_state)
            if not revision.user and state == PC_DONE and last_state == PC_OPEN:
                user = {
                    "username": "system",
                    "first_name": "Auto-end",
                    "last_name": "",
                    "id": "00000000-0000-0000-0000-000000000000",
                    "content_type": "accounts.user"
                }
            else:
                user = UserDisplaySerializer().to_representation(revision.user)
            last_state = state
            return user

        if hasattr(patrol, "revisions"):
            revisions = list(patrol.revisions)
        else:
            revisions = list(
                iter(patrol.revision.all_user().order_by('sequence')))

        result = [
            dict(
                message='{action}'.format(
                    action=self.get_action(
                        revision, field_mapping, verbose_name),
                    user=get_user_display(revision.user)
                ),
                time=revision.revision_at.isoformat(),
                user=get_user(revision),
                type=self.get_patrol_update_type(revision))
            for revision in revisions if (revision.action == AC_ADDED) or
                                         (revision.action == AC_RELATION_DELETED) or
                                         (revision.action == AC_UPDATED
                                          and set(field_mapping.keys()) & set(revision.data.keys()))
        ]
        return result

    def _update_patrol_state(self, validated_data):
        now = datetime.datetime.now(tz=pytz.utc)
        state = validated_data.get("state")
        patrol_segments = validated_data.get("patrol_segments")

        if patrol_segments and state and state != PC_CANCELLED:
            for segment in patrol_segments:
                if segment.get('time_range') and segment['time_range'].lower and segment['time_range'].upper:
                    if segment['time_range'].upper < now:
                        return PC_DONE
        return state


class PatrolTemplateSerializer(BaseSerializer):
    title = serializers.CharField()
    recurrence_rules = serializers.CharField()
    patrol_type = serializers.CharField()
    length = serializers.CharField()
    alert_rule = AlertRuleSerializer()
    source = EventSourceSerializer()
