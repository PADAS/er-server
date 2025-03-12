import logging

from rest_framework import serializers

from activity.models import EventCategory, EventType
from activity.serializers.eventtype_meta_schemas import main_event_type_schema
from activity.serializers.fields.json_schema import JSONSchemaField

logger = logging.getLogger(__name__)


class EventTypeSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="value", queryset=EventCategory.objects.all())
    has_events_assigned = serializers.SerializerMethodField()
    schema = JSONSchemaField(meta_schema=main_event_type_schema)

    serializer_url_field = "value"
    url = serializers.HyperlinkedIdentityField(view_name="v2-eventtype-detail", lookup_field="value")

    class Meta:
        model = EventType
        read_only_fields = (
            "id",
            "url",
            "has_events_assigned",
            "icon_id",
        )
        write_only_fields = (
            "icon",
            "schema",
        )
        fields = (
            read_only_fields
            + write_only_fields
            + (
                "value",
                "display",
                "ordernum",
                "is_collection",
                "category",
                "is_active",
                "default_priority",
                "default_state",
                "geometry_type",
                "resolve_time",
                "auto_resolve",
            )
        )

    def get_has_events_assigned(self, obj) -> bool:
        """
        Returns whether the event type is being used in any event.
        Implementation is based on the `in_use` annotation in the queryset.
        Avoids the to perform a separate query to check if the event type is in use.
        """
        if hasattr(obj, "in_use"):
            return obj.in_use
        logger.warning("Missing `in_use` annotation in EventType queryset for EventType %s", obj.value)
        return obj.event_set.exists()
