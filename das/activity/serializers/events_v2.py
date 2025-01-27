from typing import List

from rest_framework import serializers

from activity.models import EventCategory, EventType
from activity.serializers.events import SimplifiedEventTypeSerializer
from activity.serializers.helpers import get_allowed_actions_for_category
from utils.categories import EventCategoryRelatedPermissionSetActions


class EventCategorySerializer(serializers.HyperlinkedModelSerializer):
    permissions = serializers.SerializerMethodField()
    permission_set_changed = serializers.SerializerMethodField(read_only=True)
    event_types = SimplifiedEventTypeSerializer(many=True, read_only=True, source="eventtype_set")

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
            "permissions",
            "event_types",
            "permission_set_changed",
        )

    def get_permissions(self, obj) -> List[str]:
        user = getattr(self.context.get("request", None), "user", None)
        if user is not None:
            return get_allowed_actions_for_category(user, obj.value)

    def get_permission_set_changed(self, obj) -> bool:
        related_permissions_actions = EventCategoryRelatedPermissionSetActions(event_category=obj)
        return related_permissions_actions.is_event_category_permission_set_changed_by_user()

    def get_fields(self):
        fields = super().get_fields()

        if not self.context.get("include_event_types", False):
            fields.pop("event_types")
        if not self.context.get("include_permission_set_changed", False):
            fields.pop("permission_set_changed")
        if not self.context.get("include_permissions", False):
            fields.pop("permissions")

        return fields


class EventTypeSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="value", queryset=EventCategory.objects.all())
    has_events_assigned = serializers.SerializerMethodField()
    schema = serializers.CharField(write_only=True, allow_blank=True)
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
        Returns whether the event type is currently in use.
        Implementation is based on the `in_use` annotation in the queryset.
        Avoids the to perform a separate query to check if the event type is in use.
        """
        return obj.in_use
