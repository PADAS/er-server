from activity.models import Event, EventDetails, EventType
from drf_extra_fields.geo_fields import PointField
from rest_framework import serializers


class EventDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventDetails
        fields = [
            "data",
        ]


class EventSerializer(serializers.ModelSerializer):
    event_type = serializers.PrimaryKeyRelatedField(queryset=EventType.objects)
    events = EventDetailSerializer(many=True)
    location = PointField(required=False)

    class Meta:
        model = Event
        fields = [
            "title",
            "event_type",
            "events",
            "location"
        ]

    def create(self, validated_data):
        event_details = validated_data.pop("events")
        event = Event.objects.create(**validated_data)
        for event_detail in event_details:
            EventDetails.objects.create(event=event, **event_detail)
        return event
