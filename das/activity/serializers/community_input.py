from __future__ import annotations

from drf_extra_fields.geo_fields import PointField

from rest_framework.fields import CharField, DateTimeField
from rest_framework.serializers import ModelSerializer, SlugRelatedField

from activity.models import CommunityInput, Event, EventType
from activity.serializers.event_details import EventDetailsSerializer
from activity.serializers.fields.events import EventTypeRelatedField
from core.serializers import PointValidator


class CommunityInputSerializer(ModelSerializer):
    event_types = SlugRelatedField(
        queryset=EventType.objects.filter(readonly=False),
        many=True,
        slug_field="value",
    )

    class Meta:
        model = CommunityInput
        read_only_fields = ("id",)
        fields = read_only_fields + ("name", "value", "is_active", "event_types")


class CommunityInputEventSubmissionSerializer(ModelSerializer):
    """Narrow serializer for anonymous event submissions via community input.

    Whitelist-only: only fields a public submitter should ever set are exposed.
    System fields (state, timestamps, user attribution) are forced by the view
    via .save() kwargs. Provider/admin fields (eventsource, external_event_id,
    related_subjects, attributes, patrol_segments, etc.) are deliberately not
    declared here so they cannot be written from the public endpoint — bypassing
    the looser EventSerializer used by the authenticated admin path.
    """

    location = PointField(required=False, allow_null=True, validators=[PointValidator()])
    time = DateTimeField(source="event_time", required=False)
    event_type = EventTypeRelatedField(required=False)
    event_details = EventDetailsSerializer(required=False, default=dict)
    title = CharField(required=False, allow_blank=True)
    message = CharField(required=False, allow_blank=True)

    class Meta:
        model = Event
        read_only_fields = ("id",)
        fields = read_only_fields + ("event_type", "title", "message", "location", "time", "event_details")

    def create(self, validated_data):
        details_data = {}
        if "event_details" in validated_data:
            details_data["event_details"] = validated_data.pop("event_details")
        new_event = Event.objects.create_event(**validated_data)
        if details_data:
            EventDetailsSerializer(context=self.context).update(new_event, details_data)
        return Event.objects.get(id=new_event.id)
