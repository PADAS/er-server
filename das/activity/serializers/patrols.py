import copy
import datetime
import json

import pytz

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from rest_framework.fields import DateTimeField
from rest_framework.serializers import (
    CharField,
    CurrentUserDefault,
    HiddenField,
    IntegerField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    Serializer,
    SerializerMethodField,
    UUIDField,
    ValidationError,
)

import utils
from accounts.serializers import UserDisplaySerializer, get_user_display
from activity.models import (
    PATROL_STATE_CHOICES,
    PC_CANCELLED,
    PC_DONE,
    PC_OPEN,
    PRI_NONE,
    PRIORITY_CHOICES,
    Event,
    Patrol,
    PatrolFile,
    PatrolNote,
    PatrolSegment,
    PatrolType,
)
from activity.serializers.base import FileSerializerMixin, RevisionMixin
from core.fields import GEOPointField, choicefield_serializer, text_field
from core.serializers import BaseSerializer, PointValidator, TimestampMixin
from revision.manager import ACTION_ADDED, ACTION_RELATION_DELETED, ACTION_UPDATED
from usercontent.serializers import UserContentSerializer

priority_choices_serializer = choicefield_serializer(PRIORITY_CHOICES, default=PRI_NONE)
state_choices_serializer = choicefield_serializer(PATROL_STATE_CHOICES, default=PC_OPEN)


from .alert import AlertRuleSerializer
from .events import (
    EventRelationshipSerializer,
    EventSerializerMixin,
    EventSourceSerializer,
    EventTypeRelatedField,
)
from .fields import (
    DateTimeRangeField,
    EventRelationshipTypeRelatedField,
    LeaderRelatedField,
    PatrolTypeRelatedField,
)
from .helpers import make_feature


def update_patrol_state(validated_data):
    now = datetime.datetime.now(tz=pytz.utc)
    state = validated_data.get("state")
    patrol_segments = validated_data.get("patrol_segments")

    if patrol_segments and state and state != PC_CANCELLED:
        for segment in patrol_segments:
            if segment.get("time_range") and segment["time_range"].lower and segment["time_range"].upper:
                if segment["time_range"].upper < now:
                    return PC_DONE
    return state


class PatrolTypeSerializer(ModelSerializer):
    class Meta:
        model = PatrolType
        read_only_fields = (
            "id",
            "value",
            "display",
            "ordernum",
            "icon_id",
            "default_priority",
            "is_active",
        )
        fields = read_only_fields


class PatrolFileSerializer(FileSerializerMixin, BaseSerializer, RevisionMixin):
    """Serializer class for a PatrolFile"""

    usercontent_id = UUIDField(required=False)
    usercontent_type = PrimaryKeyRelatedField(required=False, queryset=ContentType.objects.all())

    usercontent = UserContentSerializer(required=False)

    created_by = HiddenField(default=CurrentUserDefault())

    comment = CharField(allow_blank=True, required=False)
    ordernum = IntegerField(required=False, allow_null=True)

    def create(self, validated_data):
        validated_data["patrol"] = self._kwargs.get("data").get("patrol")
        validated_data = self.pre_create(validated_data)
        return PatrolFile.objects.create(**validated_data)

    @property
    def parent_name(self):
        return "patrol"

    def get_instance_parent_id(self, instance):
        return instance.patrol.id

    def get_update_type(self, revision):
        return self.get_patrol_update_type(revision)


class OptimizedEventRelationshipSerializer(EventRelationshipSerializer):
    type = EventRelationshipTypeRelatedField()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "request" in self.context:
            request = self.context["request"]
            rep["url"] = utils.add_base_url(
                request,
                reverse(
                    "event-view-relationship",
                    args=[
                        instance.from_event_id,
                        instance.type.value,
                        instance.to_event_id,
                    ],
                ),
            )

            direction = self.context.get("event_relationship_direction", "out")
            if direction == "out":
                related_event = instance.to_event
            else:
                related_event = instance.from_event

            rep["related_event"] = PatrolSegmentEventSerializer(
                instance=related_event,
                many=False,
                context={"include_related_events": False, "request": request},
            ).data
            return rep


class PatrolSegmentEventSerializer(EventSerializerMixin, ModelSerializer):
    updated_at = DateTimeField(read_only=True)
    title = CharField(required=False, allow_blank=True)
    event_type = EventTypeRelatedField(required=False)
    contains = SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context.get("include_related_events", False):
            self.fields.pop("contains")

    class Meta:
        model = Event
        fields = (
            "id",
            "serial_number",
            "event_type",
            "priority",
            "title",
            "state",
            "contains",
            "updated_at",
        )

    def get_contains(self, event):
        return self.get_out_relation(event, "contains")

    def get_out_relation(self, event, value):
        self.context["event_relationship_direction"] = "out"
        qs = event.out_relationships.filter(type__value=value).all().order_by("ordernum", "to_event__created_at")
        serializer = OptimizedEventRelationshipSerializer(
            instance=qs,
            many=True,
            context=self.context,
        )
        return serializer.data

    def to_representation(self, event):
        rep = super().to_representation(event)
        if event.location is not None:
            geodata = make_feature(self.context["request"], event)
            rep["geojson"] = geodata

        if event.event_type:
            rep["is_collection"] = event.event_type.is_collection

        return rep


class PatrolSegmentSerializer(BaseSerializer, RevisionMixin):
    id = UUIDField(required=False, read_only=False)
    patrol = PrimaryKeyRelatedField(required=True, read_only=False, queryset=Patrol.objects.all())
    patrol_type = PatrolTypeRelatedField(required=False)
    leader = LeaderRelatedField(required=False, allow_null=True)
    scheduled_start = DateTimeField(required=False, allow_null=True)
    scheduled_end = DateTimeField(required=False, allow_null=True)
    time_range = DateTimeRangeField(required=False, allow_null=True)
    start_location = GEOPointField(required=False, allow_null=True, validators=[PointValidator()])
    end_location = GEOPointField(required=False, allow_null=True, validators=[PointValidator()])
    image_url = CharField(read_only=True, required=False)
    icon_id = CharField(read_only=True, required=False)
    events = PatrolSegmentEventSerializer(many=True, read_only=True, context={"include_related_events": True})

    def to_internal_value(self, data):
        sch_start = data.get("scheduled_start")
        sch_end = data.get("scheduled_end")

        if sch_start and sch_end and sch_start > sch_end:
            raise ValidationError("scheduled_start time has to be earlier than scheduled_end time")
        return super().to_internal_value(data)

    @staticmethod
    def resolve_image_url(patrolsegment):
        return patrolsegment.patrol_type.image_url if patrolsegment.patrol_type else None

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get("request")
        if request:
            image_url = self.resolve_image_url(instance)
            rep["image_url"] = utils.add_base_url(request, image_url)

        if rep.get("time_range") is None:
            rep["time_range"] = self.empty_timerange()

        rep["patrol_type"] = str(instance.patrol_type.value) if instance.patrol_type else None
        rep["icon_id"] = str(instance.patrol_type.icon_id) if instance.patrol_type else None
        rep["updates"] = self.render_updates(instance)
        return rep

    @staticmethod
    def empty_timerange():
        return {"start_time": None, "end_time": None}

    def create(self, validated_data):
        return PatrolSegment.objects.create(**validated_data)

    def render_updates(self, segment):
        last_scheduled_end = None

        def action(revision, fmapping):
            nonlocal last_scheduled_end
            revision_time = revision.revision_at
            scheduled_end = revision.data.get("scheduled_end", last_scheduled_end)
            if revision.action == ACTION_UPDATED:
                fieldnames = []
                for k, v in revision.data.items():
                    if k == "time_range" and v:
                        values = json.loads(v)
                        if values.get("lower"):
                            fieldnames.append("Start Time")
                        if values.get("upper"):
                            upper = parse_datetime(values.get("upper"))
                            fieldnames.append("End Time" if scheduled_end or revision_time > upper else "Auto-End Time")
                    elif k in field_mapping:
                        fieldnames.append(field_mapping.get(k))
                return "{0} fields: {1}".format(revision.get_action_display(), ", ".join(fieldnames))
            return self.get_action(revision, fmapping)

        revisions = list(iter(segment.revision.all_user().order_by("sequence")))
        field_mapping = {
            "scheduled_start": "Scheduled Start",
            "scheduled_end": "Scheduled End",
            "leader_id": "Tracking Subject",
            "start_location": "Start Location",
            "end_location": "End Location",
            "time_range": "Patrol Time",
        }

        result = [
            dict(
                message="{action}".format(
                    action=action(revision, field_mapping),
                    user=get_user_display(revision.user),
                ),
                time=revision.revision_at.isoformat(),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=self.get_patrol_update_type(revision, "segment"),
            )
            for revision in revisions
            if (revision.action == ACTION_RELATION_DELETED)
            or (revision.action == ACTION_UPDATED and set(field_mapping.keys()) & set(revision.data.keys()))
        ]

        event_results = self.render_event_updates(segment.events.all())
        result.extend(event_results)

        return sorted(result, key=lambda u: u["time"], reverse=True)

    def render_event_updates(self, events):
        results = []

        def get_action(revision, e):
            if revision.action == ACTION_ADDED:
                verbose_name = "Incident Collection" if e.event_type.is_collection else "Report"
                return f"{verbose_name} {revision.get_action_display()}"

        for event in events:
            revisions = list(iter(event.revision.all_user().order_by("sequence")))
            result = [
                dict(
                    message="{action}".format(action=get_action(revision, event)),
                    time=revision.revision_at.isoformat(),
                    user=UserDisplaySerializer().to_representation(revision.user),
                    type=self.get_patrol_update_type(revision, "event"),
                )
                for revision in revisions
                if (revision.action == ACTION_ADDED)
            ]
            results.extend(result)

            if event.out_relationships.exists():
                for o in event.out_relationships.all():
                    revisions = list(iter(o.to_event.revision.all_user().order_by("sequence")))
                    updates = [
                        dict(
                            message="Report Added",
                            time=revision.revision_at.isoformat(),
                            user=UserDisplaySerializer().to_representation(revision.user),
                            type=self.get_patrol_update_type(revision, "event"),
                        )
                        for revision in revisions
                        if (revision.action == ACTION_ADDED)
                    ]
                    results.extend(updates)

        return results


class PatrolList(Serializer):
    pass


class PatrolNoteSerializer(BaseSerializer, TimestampMixin, RevisionMixin):
    id = UUIDField(required=False, read_only=False)
    text = text_field()
    created_by_user = HiddenField(default=CurrentUserDefault())

    def create(self, validated_data):
        validated_data["patrol"] = self._kwargs.get("data").get("patrol")
        return PatrolNote.objects.create(**validated_data)

    def to_representation(self, note):
        rep = super().to_representation(note)
        rep["updates"] = self.render_updates(note)
        return rep

    def render_updates(self, note):
        def get_action(revision):
            if revision.action == ACTION_UPDATED:
                field_mapping = {"text": "Note Text"}
                fieldnames = [field_mapping[k] for k in revision.data.keys() if k in field_mapping]
                return f"{revision.get_action_display()} fields: {', '.join(fieldnames)}"

            return revision.get_action_display()

        result = [
            dict(
                message="Note {action}".format(action=get_action(revision), user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get("text", ""),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=self.get_patrol_update_type(revision, "note"),
            )
            for revision in note.revision.all_user()
        ]
        return sorted(result, key=lambda u: u["time"], reverse=True)


class PatrolTemplateSerializer(BaseSerializer):
    title = CharField()
    recurrence_rules = CharField()
    patrol_type = CharField()
    length = CharField()
    alert_rule = AlertRuleSerializer()
    source = EventSourceSerializer()


class TrackedBySerializer(Serializer):
    leader = LeaderRelatedField(read_only=True)


class PatrolSerializer(BaseSerializer, TimestampMixin, RevisionMixin):
    """Serializer class for a Patrol"""

    objective = text_field(required=False, allow_blank=True, allow_null=True)
    priority = priority_choices_serializer
    serial_number = IntegerField(read_only=True)
    state = state_choices_serializer
    title = CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    files = PatrolFileSerializer(many=True, required=False, read_only=True)
    notes = PatrolNoteSerializer(many=True, required=False)
    patrol_segments = PatrolSegmentSerializer(many=True, required=False, excludes=["patrol"])

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        for seg in rep.get("patrol_segments", []):
            seg.pop("patrol", 0)
        if self.context.get("include_updates", True):
            updates = self.render_updates(instance)
            rep["updates"] = sorted(updates, key=lambda u: u["time"], reverse=True)

        return rep

    def validate(self, attrs):
        if attrs.get("state"):
            attrs["state"] = update_patrol_state(attrs)
        return super().validate(attrs)

    def create(self, validated_data):
        patrol_notes = validated_data.pop("notes", [])
        patrol_segments = validated_data.pop("patrol_segments", [])

        new_patrol = Patrol.objects.create(**validated_data)
        for note in patrol_notes:
            note = copy.deepcopy(note)
            note["patrol_id"] = new_patrol.id
            PatrolNote.objects.create(**note)

        for segment in patrol_segments:
            segment = copy.deepcopy(segment)
            segment["patrol_id"] = new_patrol.id
            PatrolSegment.objects.create(**segment)

        return Patrol.objects.get(id=new_patrol.id)

    def update(self, instance, validated_data):
        patrol_id = instance.id
        patrol_notes = validated_data.get("notes", [])
        patrol_segments = validated_data.get("patrol_segments", [])

        self.create_update(patrol_id, patrol_notes, PatrolNote)
        self.create_update(patrol_id, patrol_segments, PatrolSegment)

        instance.priority = validated_data.get("priority", instance.priority)
        instance.state = validated_data.get("state", instance.state)
        instance.title = validated_data.get("title", instance.title)
        instance.objective = validated_data.get("objective", instance.objective)

        instance.save()
        return instance

    def create_update(self, patrol_id, validated_data, model):
        for data in validated_data:
            data["patrol_id"] = patrol_id
            data_id = data.get("id")
            if data_id:
                instance = model.objects.get(id=data_id)
                super().update(instance, data)
            else:
                model.objects.create(**data)

    def render_updates(self, patrol):
        verbose_name = patrol._meta.verbose_name.title()
        field_mapping = {"state": "State is {}", "title": "Title"}
        last_state = None

        def get_user(revision):
            nonlocal last_state
            state = revision.data.get("state", last_state)
            if not revision.user and state == PC_DONE and last_state == PC_OPEN:
                user = {
                    "username": "system",
                    "first_name": "Auto-end",
                    "last_name": "",
                    "id": "00000000-0000-0000-0000-000000000000",
                    "content_type": "accounts.user",
                }
            else:
                user = UserDisplaySerializer().to_representation(revision.user)
            last_state = state
            return user

        if hasattr(patrol, "revisions"):
            revisions = list(patrol.revisions)
        else:
            revisions = list(iter(patrol.revision.all_user().order_by("sequence")))

        result = [
            dict(
                message=f"{self.get_action(revision, field_mapping, verbose_name)}",
                time=revision.revision_at.isoformat(),
                user=get_user(revision),
                type=self.get_patrol_update_type(revision),
            )
            for revision in revisions
            if (revision.action == ACTION_ADDED)
            or (revision.action == ACTION_RELATION_DELETED)
            or (revision.action == ACTION_UPDATED and set(field_mapping.keys()) & set(revision.data.keys()))
        ]
        return result
