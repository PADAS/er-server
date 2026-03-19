import json
import logging
from typing import List

from rest_framework import serializers

from accounts.serializers import UserDisplaySerializer
from activity.models import EventCategory, EventType
from activity.schemas.eventtype_meta_schemas import main_event_type_schema
from activity.schemas.migration.choice_processor import ResolutionStrategy
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

    def validate(self, attrs: dict) -> dict:
        """
        Extract 'readonly' from schema if present (V1 backwards compatibility),
        set it on the model field, and remove it from the schema before saving.
        """
        schema = attrs.get("schema")
        if schema and isinstance(schema, dict):
            if "readonly" in schema:
                attrs["readonly"] = schema.pop("readonly")
            attrs["schema"] = json.dumps(schema, indent=2)
        return attrs

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
    user = UserDisplaySerializer()
    updated_fields = serializers.SerializerMethodField()
    sequence = serializers.IntegerField()

    def get_time(self, obj) -> str:
        return obj.revision_at.isoformat()

    def get_action(self, obj) -> str:
        return obj.get_action_display()

    def get_updated_fields(self, obj) -> List[str]:
        """Get the fields that have been updated in this revision."""
        non_user_fields = ["updated_at", "created_at"]
        if obj.action != ACTION_ADDED and isinstance(obj.data, dict):
            updated_fields = [k for k in obj.data.keys() if k not in non_user_fields]
            return updated_fields
        return []


class ChoiceValueSerializer(serializers.Serializer):
    value = serializers.CharField()
    display = serializers.CharField()


class HardcodedChoiceResolutionRequestSerializer(serializers.Serializer):
    property_path = serializers.ListField(child=serializers.CharField())
    strategy = serializers.ChoiceField(choices=[strategy.value for strategy in ResolutionStrategy])
    choice_field_name = serializers.CharField(required=False, allow_null=True)


class HardcodedChoiceResolutionSerializer(serializers.Serializer):
    property_path = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    strategy = serializers.ChoiceField(choices=[strategy.value for strategy in ResolutionStrategy])
    choice_field_name = serializers.CharField(required=False, allow_null=True)
    missing_choices = ChoiceValueSerializer(many=True, required=False, allow_null=True, read_only=True)


class MigrationEventTypeRequestItemSerializer(serializers.Serializer):
    event_type_value = serializers.CharField(required=False, max_length=255)
    hardcoded_choices_resolutions = HardcodedChoiceResolutionRequestSerializer(many=True, required=False)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = {"event_type_value": data}

        return super().to_internal_value(data)

    def validate(self, attrs: dict) -> dict:
        event_type_value = attrs.get("event_type_value")
        if not event_type_value:
            raise serializers.ValidationError("event_type_value is required.")

        return attrs


class MigrationRequestSerializer(serializers.Serializer):
    """
    Serializer for V1 to V2 schema migration request.

    Request body:
    - dry_run: if true, preview migration without persisting changes
    - event_types: array of event type values or per-event migration request objects
    """

    dry_run = serializers.BooleanField(default=True)
    event_types = MigrationEventTypeRequestItemSerializer(many=True)

    def validate(self, attrs: dict) -> dict:
        dry_run = attrs.get("dry_run", True)
        event_types = attrs.get("event_types", [])

        if not dry_run and not event_types:
            raise serializers.ValidationError({"event_types": ["This list may not be empty when dry_run is false."]})

        return attrs


class HardcodedChoiceSerializer(serializers.Serializer):
    property_path = serializers.ListField(child=serializers.CharField())
    choices = ChoiceValueSerializer(many=True)
    resolution_options = HardcodedChoiceResolutionSerializer(many=True)


class MigrationResultSerializer(serializers.Serializer):
    """
    Serializer for a single migration result.

    Response fields per FE contract:
    - event_type: value of the event type
    - v2_schema: resulting V2 schema (or null if failed)
    - warnings: array of warning messages
    - errors: array of error messages
    - metadata: additional migration information
    """

    event_type = serializers.CharField(source="event_type_value")
    v2_schema = serializers.DictField(allow_null=True)
    warnings = serializers.ListField(child=serializers.CharField())
    errors = serializers.ListField(child=serializers.CharField())
    metadata = serializers.DictField()
    hardcoded_choices = HardcodedChoiceSerializer(many=True, allow_null=True, required=False)
