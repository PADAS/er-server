import logging
from typing import List

from rest_framework import serializers

from accounts.serializers import get_user_display
from activity.models import EventCategory, EventType
from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.serializers.fields.json_schema import JSONSchemaField
from revision.manager import ACTION_ADDED

logger = logging.getLogger(__name__)


class EventCategoryValueField(serializers.SlugRelatedField):
    """SlugRelatedField for EventCategory using 'value' as the slug."""

    def __init__(self, **kwargs):
        super().__init__(slug_field="value", **kwargs)

    def get_queryset(self):
        return EventCategory.objects.all_sort()


class EventTypeV2Serializer(serializers.ModelSerializer):
    category = EventCategoryValueField()
    has_events_assigned = serializers.SerializerMethodField()
    icon_id = serializers.SerializerMethodField()
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
        fields = read_only_fields + (
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
            "schema",
            "is_active",
            "icon",
            "version",
        )

    def get_has_events_assigned(self, instance: EventType) -> bool:
        """
        Returns whether the event type is being used in any event.
        This method avoids the need to perform a separate query by checking for the `in_use` annotation.
        """
        if hasattr(instance, "in_use"):
            return instance.in_use
        logger.warning("Missing `in_use` annotation in EventType queryset for EventType %s", instance.value)
        return instance.event_set.exists()

    def get_icon_id(self, instance: EventType) -> str:
        """Get the icon_id from the EventType instance."""
        return instance.icon_id

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


class EventTypeRevisionSerializer(serializers.Serializer):
    """Serializer for EventType revision history."""

    time = serializers.SerializerMethodField()
    action = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    updated_fields = serializers.SerializerMethodField()
    sequence = serializers.IntegerField()

    def get_time(self, obj) -> str:
        return obj.revision_at.isoformat()

    def get_action(self, obj) -> str:
        return obj.get_action_display()

    def get_user(self, obj) -> str:
        """Get the user representation for this revision."""
        if not obj.user:
            return "System"
        return get_user_display(obj.user)

    def get_updated_fields(self, obj) -> List[str]:
        """Get the fields that have been updated in this revision."""
        if obj.action != ACTION_ADDED and isinstance(obj.data, dict):
            return list(obj.data.keys())
        return []
