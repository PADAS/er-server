import copy
import logging
import traceback
from collections import OrderedDict

from django_multitenant.utils import get_current_tenant
from drf_extra_fields.geo_fields import PointField
from rest_framework_gis.serializers import GeoFeatureModelListSerializer
from versatileimagefield.serializers import VersatileImageFieldSerializer

from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Polygon
from django.db.utils import IntegrityError
from django.urls import reverse
from rest_framework.serializers import (
    LIST_SERIALIZER_KWARGS,
    CharField,
    ChoiceField,
    CurrentUserDefault,
    DateTimeField,
    DictField,
    DurationField,
    HiddenField,
    JSONField,
    ListField,
    ModelSerializer,
    PrimaryKeyRelatedField,
    RelatedField,
    Serializer,
    SerializerMethodField,
    UUIDField,
    ValidationError,
)

import utils
from accounts.serializers import UserDisplaySerializer, UserSerializer, get_user_display
from activity.event_geometries import GenericGeometryFactory
from activity.exceptions import SchemaValidationError
from activity.models import (
    PC_OPEN,
    Event,
    EventCategory,
    EventClass,
    EventClassFactor,
    EventFactor,
    EventFile,
    EventFilter,
    EventGeometry,
    EventNote,
    EventPhoto,
    EventRelatedSegments,
    EventRelatedSubject,
    EventRelationship,
    EventSource,
    EventsourceEvent,
    EventType,
    PatrolSegment,
)
from activity.util import get_permitted_event_categories
from core.serializers import PointValidator
from observations.serializers import SubjectRelatedField, SubjectSerializer
from revision.manager import ACTION_ADDED, ACTION_UPDATED, RevisionMessage
from usercontent.serializers import UserContentSerializer
from utils.categories import make_eventcategory_permission_codename
from utils.feature_representation import FeatureRepresentation
from utils.gis import get_polygon_info
from utils.json import parse_bool
from utils.schema_utils import (
    get_schema_renderer_method,
    validate_rendered_schema_is_wellformed,
)

from .base import FileSerializerMixin
from .event_details import EventDetailsSerializer
from .exceptions import DuplicateResourceException
from .fields import (
    EventGeometryField,
    EventRelationshipTypeRelatedField,
    EventSourceRelatedField,
    EventTypeRelatedField,
    ReportedByRelatedField,
)
from .geometries import EventGeometryRevisionSerializer
from .helpers import (
    get_allowed_actions_for_category,
    get_update_type,
    make_feature,
    resolve_image_url,
)

logger = logging.getLogger(__name__)


def which_field_search_for(application):
    if application and application.client_id in ("cybertracker",):
        return "reported_by"
    return None


def auto_add_report_to_patrols(application, event):
    if event.patrol_segments.exists():
        return

    field_to_search = which_field_search_for(application)

    if field_to_search:
        subject = getattr(event, field_to_search)

        if subject:
            segments = PatrolSegment.objects.filter(leader_id=subject.id, patrol__state=PC_OPEN)
            event_time = event.event_time
            for segment in segments:
                if segment.time_range and not segment.time_range.isempty and event_time in segment.time_range:
                    segment.events.add(event)


class EventCategorySerializer(ModelSerializer):
    class Meta:
        model = EventCategory
        read_only_fields = ("id",)
        fields = (
            "id",
            "value",
            "display",
            "is_active",
            "ordernum",
            "flag",
        )

    def to_representation(self, obj):
        rep = super().to_representation(obj)

        # If we know the user requesting the category, include their permissions
        # for that category
        request = self.context.get("request", None)
        user, method = getattr(request, "user", None), getattr(request, "method", None)
        if user is not None and method == "GET":
            rep["permissions"] = get_allowed_actions_for_category(user, rep["value"])
        return rep


class EventCategoryRelatedField(RelatedField):
    def to_representation(self, value):
        rep = EventCategorySerializer().to_representation(value)
        user = getattr(self.context.get("request", None), "user", None)
        if user is not None:
            rep["permissions"] = get_allowed_actions_for_category(user, rep["value"])
        return rep

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                event_category = EventCategory.objects.get_by_value(data)
            except EventCategory.DoesNotExist:
                raise ValidationError(f"event_category: {data} does not exist.")
            else:
                return event_category

    def get_queryset(self):
        return EventCategory.objects.all_sort()

    def get_choices(self, cutoff=None):
        queryset = self.get_queryset()
        if queryset is None:
            return {}

        if cutoff is not None:
            queryset = queryset[:cutoff]

        return OrderedDict([(self.to_representation(item).get("value"), self.display_value(item)) for item in queryset])


class EventTypeSerializer(ModelSerializer):
    category = EventCategoryRelatedField()

    class Meta:
        model = EventType
        read_only_fields = ("id",)
        write_only_fields = ("icon",)
        fields = (
            read_only_fields
            + write_only_fields
            + (
                "value",
                "display",
                "ordernum",
                "is_collection",
                "category",
                "icon_id",
                "is_active",
                "schema",
                "default_priority",
                "geometry_type",
            )
        )

    def __init__(self, *args, **kwargs):
        super(EventTypeSerializer, self).__init__(*args, **kwargs)
        self.request = self.context.get("request")

        if not self.context.get("include_schema", False) and self.request.method == "GET":
            self.fields.pop("schema")

    @staticmethod
    def validate_schema(schema):
        try:
            rendered_schema = get_schema_renderer_method()(schema)
        except NameError as exc:
            raise ValidationError(exc)
        except ValueError as exc:
            raise ValidationError(exc)
        except Exception as exc:
            raise ValidationError(exc)
        else:
            try:
                validate_rendered_schema_is_wellformed(rendered_schema)
            except SchemaValidationError as exc:
                raise ValidationError(exc)
        return schema

    def to_internal_value(self, data):
        if data.get("icon_id"):
            data["icon"] = data["icon_id"]

        return super().to_internal_value(data)

    @staticmethod
    def is_schema_readonly(schema):
        try:
            rendered = get_schema_renderer_method()(schema)
        except Exception:
            pass
        else:
            _schema = rendered.get("schema", {})
            return True if parse_bool(_schema.get("readonly")) else False

    def to_representation(self, obj):
        rep = super().to_representation(
            obj,
        )
        rep["url"] = utils.add_base_url(
            self.request,
            reverse(
                "eventtype",
                args=[
                    obj.id,
                ],
            ),
        )

        if self.is_schema_readonly(obj.schema):
            rep["readonly"] = True
        return rep


class EventFileSerializer(FileSerializerMixin, ModelSerializer):
    usercontent_id = UUIDField(required=False)
    usercontent_type = PrimaryKeyRelatedField(required=False, queryset=ContentType.objects.all())
    usercontent = UserContentSerializer(required=False)
    created_by = HiddenField(default=CurrentUserDefault())
    comment = CharField(allow_blank=True, required=False)

    class Meta:
        model = EventFile
        read_only_fields = ("created_at", "updated_at", "created_by")
        fields = (
            "id",
            "event",
            "comment",
            "usercontent",
            "usercontent_id",
            "usercontent_type",
        ) + read_only_fields

    @property
    def parent_name(self):
        return "event"

    def get_instance_parent_id(self, instance):
        return instance.event.id

    def get_update_type(self, revision, previous_revisions=[]):
        return get_update_type(revision, previous_revisions)


class EventNoteSerializer(ModelSerializer):
    id = UUIDField(required=False, read_only=False)
    created_by_user = HiddenField(default=CurrentUserDefault())

    class Meta:
        model = EventNote
        read_only_fields = ("created_at", "updated_at")
        write_only_fields = ("event",)
        fields = ("id", "created_by_user", "text") + write_only_fields + read_only_fields

    def to_representation(self, note):
        rep = super().to_representation(note)
        rep["updates"] = self.render_updates(note)
        return rep

    def get_display_value(self, note):
        return "{0}: {1}".format(get_user_display(note.created_by_user), note.text)

    def render_updates(self, note):
        def get_action(revision):
            if revision.action in (ACTION_ADDED, ACTION_UPDATED):
                field_mapping = {"text": "Note Text"}
                fieldnames = [value for key, value in revision.data.items() if key in field_mapping]
                return f"{revision.get_action_display()}: {', '.join(fieldnames)}"

            return revision.get_action_display()

        return [
            dict(
                message="Note {action}".format(action=get_action(revision), user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get("text", ""),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=get_update_type(revision),
            )
            for revision in note.revision.all_user()
        ]


class EventSerializerMixin:
    feature_representation = FeatureRepresentation()

    def to_internal_value(self, data):
        internal_value = super().to_internal_value(data)

        for x in ("contains", "is_linked_to", "collection"):
            if x in data:
                internal_value[x] = data[x]

        return internal_value

    def create(self, validated_data):
        return self.create_event(validated_data)

    def create_event(self, validated_data):
        details_data = {}

        if "event_details" in validated_data:
            details_data["event_details"] = validated_data["event_details"]
            del validated_data["event_details"]

        event_notes = validated_data.pop("notes", [])

        # [_.type for _ in activity.models.EventRelationshipType.objects.all()]
        rel_types = (
            "contains",
            "is_linked_to",
        )

        relationship_data = {}
        for key in rel_types + ("collection",):
            if key in validated_data:
                relationship_data[key] = validated_data.pop(key)

        related_subjects = validated_data.pop("related_subjects", ())

        eventsource = validated_data.pop("eventsource", None)
        external_event_id = validated_data.pop("external_event_id", None)

        new_event = Event.objects.create_event(**validated_data)

        EventDetailsSerializer().update(new_event, details_data)

        if eventsource and external_event_id:
            try:
                EventsourceEvent.objects.add_relation(new_event, eventsource, external_event_id)

            except IntegrityError:
                raise DuplicateResourceException(
                    fieldname="external_event_id",
                    detail="External event ID already exists.",
                )

        for note in event_notes:
            note = copy.deepcopy(note)
            note["event"] = new_event.id
            enser = EventNoteSerializer(data=note, context=self.context)
            enser = enser.is_valid(raise_exception=True)
            enser.create(enser.validated_data)

        for related_subject in related_subjects:
            EventRelatedSubject.objects.get_or_create(subject=related_subject, event=new_event)

        for relationship_type in rel_types:
            if relationship_type in relationship_data:
                related = relationship_data.pop(relationship_type)
                if not isinstance(related, (list, set)):
                    related = [
                        related,
                    ]

                children = [self.create_event(self.to_internal_value(child)) for child in related]

                for child in children:
                    EventRelationship.objects.add_relationship(
                        from_event=new_event, to_event=child, type=relationship_type
                    )

        if "collection" in relationship_data:
            parent = relationship_data.pop("collection")
            parent = Event.objects.get(id=parent["id"])
            if parent:
                EventRelationship.objects.add_relationship(from_event=parent, to_event=new_event, type="contains")

        return Event.objects.get(id=new_event.id)

    def update(self, instance, validated_data):
        logger.info("Inside update: %s", validated_data)
        update_fields = []

        patrol_segments = validated_data.pop("patrol_segments", None)
        if patrol_segments:
            logger.info("setting patrol segments. with %s", patrol_segments)
            # update_fields.append('patrol_segments')
            instance.patrol_segments.set(patrol_segments)

        for k, v in validated_data.items():
            # details don't get saved in the same table as the rest of the
            # event data, so hand this off and pretend we never saw it
            if k == "event_details":
                EventDetailsSerializer().update(instance, {k: v})
                continue
            if k == "notes":
                for note in v:
                    note = copy.deepcopy(note)
                    note["event"] = instance.id
                    note_id = note.pop("id", None)
                    enser = EventNoteSerializer(data=note, context=self.context)
                    enser.is_valid(raise_exception=True)
                    if note_id:
                        note_instance = EventNote.objects.get(id=note_id)
                        enser.update(note_instance, enser.validated_data)
                    else:
                        enser.create(enser.validated_data)
                continue

            if getattr(instance, k) != v:
                setattr(instance, k, v)
                if k == "reported_by":
                    update_fields.append("reported_by_id")
                    update_fields.append("reported_by_content_type_id")
                elif k not in ("id",):
                    update_fields.append(k)

        if update_fields:
            instance.save(update_fields=update_fields)
        return instance

    def render_updates(self, event):
        result = []

        if hasattr(event, "revisions"):
            revisions = list(iter(event.revisions))
        else:
            revisions = list(iter(event.revision.all_user().order_by("sequence")))

        while revisions:
            revision = revisions.pop()
            action = RevisionMessage.get_action(revision, event)
            if action:
                record = dict(
                    message=f"{action}",
                    time=revision.revision_at.isoformat(),
                    user=self.get_revision_user(revision.user, event),
                    type=get_update_type(revision, revisions),
                )
                result.append(record)
        return result

    def get_user_display(self, user, event):
        if user:
            return get_user_display(user)
        return event.get_provenance_display()

    def get_revision_user(self, user, event):
        if user:
            return UserDisplaySerializer().to_representation(user)
        return {
            "first_name": event.get_provenance_display(),
            "last_name": "",
            "username": event.provenance,
        }

    def get_geojson(self, request, event):
        geojson = None
        if geometry := event.geometries.first():
            geojson = self.feature_representation.get_feature(request, geometry)
        if hasattr(event, "location") and event.location:
            point_geojson = self.feature_representation.get_feature(request, event)
            if geojson:
                geo_collection = utils.json.empty_geojson_featurecollection()
                geo_collection["features"].extend((geojson, point_geojson))
                geojson = geo_collection
            else:
                geojson = point_geojson
        return geojson


class EventHeaderSerializer(EventSerializerMixin, ModelSerializer):
    """
    This is intended to serialize only 'header' fields for an Event, and especially to avoid
    serializing nested events.
    """

    event_type = EventTypeRelatedField(required=False)
    updated_at = DateTimeField(source="sort_at", required=False, read_only=True)

    class Meta:
        model = Event
        fields = (
            "id",
            "message",
            "time",
            "end_time",
            "serial_number",
            "priority",
            "event_type",
            "icon_id",
            "created_at",
            "updated_at",
            "title",
            "state",
        )

    def to_representation(self, event):
        rep = super().to_representation(event)
        if "request" in self.context:
            request = self.context["request"]
            rep["url"] = utils.add_base_url(
                request,
                reverse(
                    "event-view",
                    args=[
                        event.id,
                    ],
                ),
            )

            image_url = resolve_image_url(event)
            rep["image_url"] = utils.add_base_url(request, image_url)
            rep["geojson"] = self.get_geojson(request, event)

        if event.event_type and event.event_type.category:
            rep["event_category"] = event.event_type.category.value

        rep["is_collection"] = event.event_type.is_collection

        return rep


class EventRelationshipSerializer(ModelSerializer):
    def to_internal_value(self, data):
        return super().to_internal_value(data)

    type = EventRelationshipTypeRelatedField()

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        if "request" in self.context:
            request = self.context["request"]

            # 'url' represents the proper relationship (from_event : to_event) regardless of the direction of this
            # serialization.
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

        # related_event = instance.to_event if direction == 'out' else instance.from_event

        rep["related_event"] = EventHeaderSerializer(instance=related_event, many=False, context=self.context).data

        return rep

    def validate(self, attrs):
        to_event_id = attrs.get("to_event_id")
        if to_event_id and to_event_id == self.instance.from_event.id:
            raise ValidationError("An event may not be related to itself.")
        return super().validate(attrs)

    class Meta:
        model = EventRelationship
        read_only_fields = (
            "created_at",
            "updated_at",
        )
        fields = (
            "type",
            "ordernum",
        )


class EventSourceSerializer(ModelSerializer):
    event_type = EventTypeRelatedField(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = EventSource
        read_only_fields = ("id",)
        fields = read_only_fields + (
            "eventprovider",
            "external_event_type",
            "display",
            "event_type",
            "additional",
            "is_ready",
        )

    def to_representation(self, obj):
        rep = super().to_representation(
            obj,
        )
        rep["url"] = utils.add_base_url(
            self.context["request"],
            reverse(
                "eventsource-view",
                args=[
                    obj.id,
                ],
            ),
        )
        return rep

    def validate(self, data):
        tenant = get_current_tenant()
        event_provider = data.get("eventprovider")
        external_event_type = data.get("external_event_type")
        if tenant and event_provider and external_event_type:
            event_source = EventSource.objects.filter(
                das_tenant=tenant,
                eventprovider=data["eventprovider"],
                external_event_type=data["external_event_type"],
            ).exists()
            if event_source:
                raise ValidationError("Unique constrain error in EventSource model.")
        return data


class EventProviderSerializer(ModelSerializer):
    owner = HiddenField(default=CurrentUserDefault())

    class Meta:
        model = EventSource
        read_only_fields = ("id", "owner")
        fields = read_only_fields + ("display", "additional", "is_active")

    def to_representation(self, obj):
        rep = super().to_representation(
            obj,
        )

        rep["owner"] = UserSerializer().to_representation(obj.owner)

        rep["url"] = utils.add_base_url(self.context["request"], reverse("eventprovider-view", args=[obj.id]))

        return rep


class EventRelatedSegmentSerializer(ModelSerializer):
    class Meta:
        model = EventRelatedSegments
        fields = ("event", "patrol_segment")


class EventFilterSpecificationSerializer(Serializer):
    text = CharField(required=False, allow_blank=True, max_length=100)

    date_range = DictField(required=False, child=DateTimeField())
    duration = DurationField(required=False)
    priority = ListField(
        required=False,
        child=ChoiceField(choices=[x[0] for x in Event.PRIORITY_CHOICES]),
    )
    state = ListField(required=False, child=ChoiceField(choices=[x[0] for x in Event.STATE_CHOICES]))

    event_category = ListField(required=False, child=CharField())

    event_type = ListField(required=False, child=CharField())

    reported_by = ListField(required=False, child=CharField())

    def validate_date_range(self, value):
        if "lower" in value and "upper" in value and value["lower"] > value["upper"]:
            raise ValidationError("Invalid date range.")
        return value


class EventFilterSerializer(ModelSerializer):
    filter_spec = JSONField()
    filter_name = CharField()

    class Meta:
        model = EventFilter
        fields = ("id", "filter_name", "ordernum", "filter_spec", "is_hidden")

    def validate_filter_spec(self, attrs):
        EventFilterSpecificationSerializer().run_validation(attrs)
        return super().validate(attrs)

    def create(self, validated_data):
        ef = EventFilter.objects.create(**validated_data)
        return ef


class EventSerializer(EventSerializerMixin, ModelSerializer):
    serializer_choice_field = ChoiceField
    # Using PointField here provides the magic to convert between a
    #  json {lat/lon} and our internal representation.
    location = PointField(required=False, allow_null=True, validators=[PointValidator()])
    geometry = EventGeometryField(source="geometries", required=False, allow_null=True)
    time = DateTimeField(source="event_time", required=False)
    created_at = DateTimeField(required=False)
    updated_at = DateTimeField(source="sort_at", required=False)
    sort_at = DateTimeField(
        required=False,
    )
    created_by_user = HiddenField(default=CurrentUserDefault())
    notes = EventNoteSerializer(many=True, required=False)
    reported_by = ReportedByRelatedField(required=False, allow_null=True)
    message = CharField(required=False, allow_blank=True)
    comment = CharField(required=False, allow_blank=True)
    title = CharField(required=False, allow_blank=True)
    # photos = EventPhotoSerializer(many=True, required=False)
    event_type = EventTypeRelatedField(required=False)
    event_details = EventDetailsSerializer(required=False, default={})

    eventsource = EventSourceRelatedField(required=False)

    external_event_id = CharField(max_length=100, required=False)

    contains = SerializerMethodField()
    is_linked_to = SerializerMethodField()
    is_contained_in = SerializerMethodField()

    files = EventFileSerializer(many=True, required=False, read_only=True)

    related_subjects = SubjectRelatedField(many=True, required=False)

    patrol_segments = PrimaryKeyRelatedField(many=True, required=False, queryset=PatrolSegment.objects.all())

    def create(self, validated_data):
        geometries = validated_data.pop("geometries", None)
        instance = super().create(validated_data)

        if geometries:
            self._create_geometries(instance, geometries)

        request = self.context["request"]
        if hasattr(request, "auth") and request.auth:
            auto_add_report_to_patrols(request.auth.application, instance)

        return instance

    def update(self, instance, validated_data):
        geometries_exits = "geometries" in validated_data
        geometries = validated_data.pop("geometries", None)
        instance = super().update(instance, validated_data)

        if geometries:
            self._update_latest_geometry(instance, geometries)
        else:
            if geometries_exits:
                self._delete_event_geometries(instance)

        return instance

    def get_contains(self, event):
        self.context["event_relationship_direction"] = "out"
        return self._get_event_relationship(event=event, relationship_name="relationship_out_contains")

    def get_is_linked_to(self, event):
        self.context["event_relationship_direction"] = "out"
        return self._get_event_relationship(event=event, relationship_name="relationship_out_is_linked_to")

    def get_is_contained_in(self, event):
        self.context["event_relationship_direction"] = "in"
        return self._get_event_relationship(event=event, relationship_name="relationship_in_contains")

    def _get_event_relationship(self, event: "Event", relationship_name: str) -> EventRelationshipSerializer:
        if not hasattr(event, f"{relationship_name}"):
            fallback_events_mapping = {
                "relationship_in_contains": "contains",
                "relationship_out_is_linked_to": "is_linked_to",
                "relationship_out_contains": "contains",
            }
            return (
                self.get_in_relation(event=event, value=fallback_events_mapping[relationship_name])
                if relationship_name == "relationship_in_contains"
                else self.get_out_relation(event=event, value=fallback_events_mapping[relationship_name])
            )

        events_mapping = {
            "relationship_in_contains": event.relationship_in_contains,
            "relationship_out_is_linked_to": event.relationship_out_is_linked_to,
            "relationship_out_contains": event.relationship_out_contains,
        }
        return EventRelationshipSerializer(events_mapping[relationship_name], many=True, context=self.context).data

    def validate(self, attrs):
        event_type = attrs.get("event_type")
        event_source = attrs.get("eventsource")
        location = attrs.get("location")
        geometries = attrs.get("geometries")
        end_time = attrs.get("end_time")
        priority = attrs.get("priority")
        state = attrs.get("state")
        external_event_id = attrs.get("external_event_id")

        if event_type and self._is_event_type_geometry(event_type) and location:
            raise ValidationError({"location": "This field is not allowed for events with polygon type."})

        if event_type and self._is_event_type_point(event_type) and geometries:
            raise ValidationError({"geometry": "This field is not allowed for events with point type."})

        if end_time and end_time < self.instance.time:
            raise ValidationError("Event end_time must not be earlier than event time.")

        # For creating an event, if event_type is not present in the request, raise ValidationError.
        if not self.instance:
            if not event_type:
                if event_source and event_source.event_type:
                    attrs["event_type"] = event_source.event_type
                else:
                    raise ValidationError({"event_type": "Event type must be provided."})

            if self._is_event_source_duplicated(event_source, external_event_id):
                raise DuplicateResourceException(
                    fieldname="external_event_id",
                    detail="External event ID already exists.",
                )

            # Set default priority from event type if not provided in POST.
            if not priority and event_type:
                attrs["priority"] = event_type.default_priority
            if not state and event_type:
                attrs["state"] = event_type.default_state
        return super().validate(attrs)

    def get_out_relation(self, event, value):
        self.context["event_relationship_direction"] = "out"
        request = self.context.get("request")
        permitted_categories = get_permitted_event_categories(request)

        qs = (
            event.out_relationships.filter(
                to_event__event_type__category__in=permitted_categories,
                type__value=value,
            )
            .all()
            .order_by("ordernum", "to_event__created_at")
        )

        serializer = EventRelationshipSerializer(
            instance=qs,
            many=True,
            context=self.context,
        )
        return serializer.data

    def get_in_relation(self, event, value):
        qs = event.in_relationships.filter(type__value=value).all()
        self.context["event_relationship_direction"] = "in"
        serializer = EventRelationshipSerializer(
            instance=qs,
            many=True,
            context=self.context,
        )
        return serializer.data

    class Meta:
        model = Event
        read_only_fields = (
            "updated_at",
            "created_at",
            "icon_id",
            "serial_number",
        )
        default_fields = (
            "id",
            "location",
            "time",
            "end_time",
            "message",
            "provenance",
            "event_type",
            "priority",
            "priority_label",
            "attributes",
            "comment",
            "title",
            "created_by_user",
            "notes",
            "reported_by",
            "state",
            "event_details",
            "contains",
            "is_linked_to",
            "is_contained_in",
            "files",
            "related_subjects",
            "eventsource",
            "external_event_id",
            "sort_at",
            "patrol_segments",
            "geometry",
        )
        fields = (*default_fields, *read_only_fields)

    def __init__(self, *args, **kwargs):
        self._event_geometry_factory = GenericGeometryFactory()

        super().__init__(*args, **kwargs)

        if self.context.get("include_files", True):
            self.fields["files"].context.update(self.context)
        else:
            self.fields.pop("files")

        if self.context.get("include_notes", True):
            self.fields["notes"].context.update(self.context)
        else:
            self.fields.pop("notes")

        if self.context.get("include_details", True):
            self.fields["event_details"].context.update(self.context)
        else:
            self.fields.pop("event_details")

        if not self.context.get("include_related_events", False):
            self.fields.pop("contains")
            self.fields.pop("is_linked_to")

    def to_representation(self, event):
        self.fields.pop("eventsource", None)

        set_prefetched = hasattr(event, "event_details_set")

        if set_prefetched:
            # pop the following out of the representation if we've prefetched using the _set
            self.fields.pop("event_details", None)
            self.fields.pop("files", None)
            self.fields.pop("related_subjects", None)

        rep = super().to_representation(event)

        details_updates = ""

        if set_prefetched:
            # Apply the prefetched data back to the representation
            try:
                event_details_serialized = EventDetailsSerializer(
                    event.event_details_set, many=True, context=self.context
                ).data
                rep["event_details"] = {}
                if event_details_serialized:
                    rep["event_details"] = event_details_serialized[0]
                rep["files"] = list(EventFileSerializer(event.files_set, many=True, context=self.context).data)
                rep["related_subjects"] = list(
                    SubjectSerializer(event.related_subjects_set, many=True, context=self.context, read_only=True).data
                )
                event_details = rep["event_details"]
                if event_details:
                    details_updates = event_details.get("updates")
            except Exception as ex:
                logger.exception("Failed Event pre-fetched  {}".format(ex))
        else:
            event_details = rep["event_details"]

            if rep["event_details"] is not None:
                details_updates = rep["event_details"].pop("updates")

        try:
            event_source = event.eventsource_event_refs.first().eventsource
        except:
            pass
        else:
            if event_source and event_source.eventprovider:
                rep["external_source"] = {
                    "url": event_source.eventprovider.additional.get("external_event_url"),
                    "text": event_source.eventprovider.display,
                    "icon_url": event_source.eventprovider.additional.get("icon_url"),
                }
        if "request" in self.context:
            request = self.context["request"]

            if event.event_type and event.event_type.category:
                category_name = event.event_type.category.value
                rep["event_category"] = category_name
                permission_name = f"activity.{category_name}_read"
                geo_permission_name = make_eventcategory_permission_codename(
                    event.event_type.category.value, "view", True, "activity"
                )

                if not request.user.has_perm(permission_name) and not request.user.has_perm(geo_permission_name):
                    rep = {"id": rep["id"]}
                    return rep

            rep["url"] = utils.add_base_url(
                request,
                reverse(
                    "event-view",
                    args=[
                        event.id,
                    ],
                ),
            )
            image_url = resolve_image_url(event)
            rep["image_url"] = utils.add_base_url(request, image_url)

            rep["geojson"] = self.get_geojson(request, event)

        if event.event_type:
            rep["is_collection"] = event.event_type.is_collection

        # This is to fix https://vulcan.atlassian.net/browse/DAS-6264
        # TODO: Consider adjusting the context within the listed Views.
        if self.context.get("include_updates", True) and not getattr(
            self.context.get("view", None), "get_view_name", lambda: None
        )() in ("Patrols", "Patrol", "Patrolsegment"):
            updates = self.render_updates(event)
            for note in rep.get("notes", []):
                updates.extend(note["updates"])

            for f in rep.get("files", []):
                updates.extend(f["updates"])

            for geometry in self._render_geometries_updates(event):
                updates.extend(geometry)

            if event_details:
                updates.extend(details_updates)

            rep["updates"] = sorted(updates, key=lambda u: u["time"], reverse=True)

        patrol_ids = (
            event.patrol_ids if hasattr(event, "patrol_ids") else Event.objects.get_related_patrol_ids(event=event)
        )

        rep["patrols"] = [item for item in patrol_ids if item is not None]
        return rep

    def _render_geometries_updates(self, event) -> list:
        if not hasattr(event, "geometries"):
            return []

        return [
            EventGeometryRevisionSerializer(geometry.revision.all(), many=True).data
            for geometry in event.geometries.all()
        ]

    def _create_geometries(self, event: Event, geometry: dict):
        geometry_type = geometry.get("type")

        if geometry_type == "Feature":
            self._create_geometry(event, geometry)
        elif geometry_type == "FeatureCollection":
            for feature in geometry.get("features"):
                self._create_geometry(event, feature)

    def _create_geometry(self, event: Event, geometry: dict):
        sort = geometry.get("geometry", {}).get("type")
        coordinates = geometry.get("geometry").get("coordinates", [[]])[0]
        properties = geometry.get("properties", {})

        event_geometry = self._event_geometry_factory.create_event_geometry(sort)
        event_geometry.create(event, coordinates, properties)

    def _update_latest_geometry(self, event: Event, geometry: dict):
        latest_event_geometry = EventGeometry.objects.filter(event=event).last()

        if latest_event_geometry:
            feature_type = geometry.get("type")
            if feature_type == "Feature":
                self._update_geometry(geometry, latest_event_geometry)
            elif feature_type == "FeatureCollection":
                for feature in geometry.get("features"):
                    self._update_geometry(feature, latest_event_geometry)
        else:
            self._create_geometries(event, geometry)

    def _update_geometry(self, geometry: dict, event_geometry: EventGeometry):
        coordinates = geometry.get("geometry").get("coordinates")[0]
        properties = geometry.get("properties", {})
        polygon = Polygon(coordinates, srid=4326)
        properties["area"] = get_polygon_info(polygon, "area")
        properties["perimeter"] = get_polygon_info(polygon, "length")

        try:
            event_geometry.properties = properties
            event_geometry.geometry = polygon
            event_geometry.save()
        except Exception as e:
            logger.exception(f"Error {e} trying to update a EventGeometry.")

    def _delete_event_geometries(self, event):
        event.geometries.all().delete()

    def _is_event_type_geometry(self, event_type: EventType):
        return event_type.geometry_type == EventType.GeometryTypesChoices.POLYGON.label

    def _is_event_type_point(self, event_type: EventType):
        return event_type.geometry_type == EventType.GeometryTypesChoices.POINT.label

    def _is_event_source_duplicated(self, event_source, external_event_id):
        return EventsourceEvent.objects.filter(eventsource=event_source, external_event_id=external_event_id).exists()


class EventStateSerializer(ModelSerializer):
    class Meta:
        model = Event
        fields = ("state",)

    def update(self, instance, validated_data):
        update_fields = []
        for k, v in validated_data.items():
            if getattr(instance, k) != v:
                setattr(instance, k, v)
                update_fields.append(k)
        if update_fields:
            instance.save(update_fields=update_fields)
        return instance


class EventPhotoSerializer(ModelSerializer):
    created_by_user = HiddenField(default=CurrentUserDefault())

    image = VersatileImageFieldSerializer(sizes="event_photo")

    class Meta:
        model = EventPhoto
        read_only_fields = (
            "created_at",
            "updated_at",
            "created_by_user",
        )
        fields = ("id", "image", "filename", "event") + read_only_fields

    def to_representation(self, photo):
        rep = super().to_representation(photo)
        rep["updates"] = self.render_updates(photo)
        if "request" in self.context:
            rep["url"] = utils.add_base_url(
                self.context["request"],
                reverse("event-view-photo", args=[photo.event.id, photo.id]),
            )
        else:
            logger.warning(
                "missing request in EventPhotoSerializer context: %s",
                traceback.format_stack(),
            )

        return rep

    def render_updates(self, photo):
        def get_action(revision):
            return revision.get_action_display()

        return [
            dict(
                message="Photo {action}".format(action=get_action(revision), user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get("text", ""),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=get_update_type(revision),
            )
            for revision in photo.revision.all_user()
        ]


class EventGeoJsonSerializer(EventSerializer):
    fields_to_copy = (
        "id",
        "event_type",
        "serial_number",
        "time",
        "priority",
        "priority_label",
        "title",
        "state",
        "event_details",
        "created_at",
        "updated_at",
        "event_category",
        "is_collection",
    )

    @classmethod
    def many_init(cls, *args, **kwargs):
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {"child": child_serializer}
        list_kwargs.update(dict([(key, value) for key, value in kwargs.items() if key in LIST_SERIALIZER_KWARGS]))
        meta = getattr(cls, "Meta", None)
        list_serializer_class = getattr(meta, "list_serializer_class", GeoFeatureModelListSerializer)
        return list_serializer_class(*args, **list_kwargs)

    def create(self, validated_data):
        raise NotImplementedError("Create Event using GeoJson not supported")

    def to_representation(self, event):
        rep = super().to_representation(event)
        event_rep = rep.get("geojson")
        if not event_rep:
            if "request" in self.context:
                event_rep = make_feature(self.context["request"], event)
        if not event_rep:
            event_rep = utils.json.empty_geojson_feature()

        properties = event_rep["properties"]

        for name in self.fields_to_copy:
            if name in rep and name not in properties:
                properties[name] = rep[name]

        return event_rep


class EventClassSerializer(ModelSerializer):
    class Meta:
        model = EventClass
        fields = ("value", "display", "ordernum")


class EventFactorSerializer(ModelSerializer):
    class Meta:
        model = EventFactor
        fields = ("value", "display", "ordernum")


class EventClassFactorSerializer(ModelSerializer):
    class Meta:
        model = EventClassFactor
        fields = ("value",)

    def to_representation(self, instance):
        c = instance.eventclass
        f = instance.eventfactor
        rep = dict(
            value=instance.value,
            class_value=c.value,
            factor_value=f.value,
            priority=instance.priority,
            priority_label=instance.get_priority_display(),
        )

        return rep
