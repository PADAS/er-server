import logging

from rest_framework import serializers

from activity.models import EventCategory, EventType
from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.serializers.fields.json_schema import JSONSchemaField

logger = logging.getLogger(__name__)


class EventCategoryValueField(serializers.SlugRelatedField):
    """SlugRelatedField for EventCategory using 'value' as the slug."""

    def __init__(self, **kwargs):
        super().__init__(slug_field="value", **kwargs)

    def get_queryset(self):
        return EventCategory.objects.all_sort()


class EventTypeSerializer(serializers.ModelSerializer):
    category = EventCategoryValueField()
    has_events_assigned = serializers.SerializerMethodField()
    schema = JSONSchemaField(meta_schema=main_event_type_schema, validate_sections=True)
    version = serializers.HiddenField(default=EventType.VersionChoices.VERSION_2)
    url = serializers.HyperlinkedIdentityField(
        view_name="v2-eventtype-detail", lookup_field="value", lookup_url_kwarg="eventtype_value"
    )

    class Meta:
        model = EventType
        read_only_fields = (
            "id",
            "url",
            "has_events_assigned",
            "icon_id",
        )
        write_only_fields = ("icon", "schema")
        fields = (
            read_only_fields
            + write_only_fields
            + (
                "value",
                "display",
                "ordernum",
                "category",
                "geometry_type",
                "default_priority",
                "default_state",
                "resolve_time",
                "auto_resolve",
                "readonly",
                "is_collection",
                "is_active",
                "version",
            )
        )

    def get_has_events_assigned(self, instance: EventType) -> bool:
        """
        Returns whether the event type is being used in any event.
        Implementation is based on the `in_use` annotation in the queryset.
        Avoids the to perform a separate query to check if the event type is in use.
        """
        if hasattr(instance, "in_use"):
            return instance.in_use
        logger.warning("Missing `in_use` annotation in EventType queryset for EventType %s", instance.value)
        return instance.event_set.exists()

    def to_representation(self, instance: EventType) -> dict:
        """
        Override to add / remove schema field based on `include_schema`,
        gathered from the request query params in the view.
        """
        representation = super().to_representation(instance)
        include_schema = self.context.get("include_schema", False)

        if not include_schema:
            representation.pop("schema", None)

        return representation
