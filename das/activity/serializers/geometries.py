from rest_framework import serializers

from accounts.serializers import UserDisplaySerializer
from activity.models import Event, EventGeometry
from revision.manager import ACTION_ADDED, ACTION_UPDATED


class EventGeometryRevisionSerializer(serializers.Serializer):
    message = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()

    def get_message(self, obj):
        if obj.action == ACTION_ADDED:
            return "Added Area"
        elif obj.action == ACTION_UPDATED:
            return "Changed Area"
        return obj.get_action_display()

    def get_time(self, obj):
        return obj.revision_at.isoformat()

    def get_type(self, obj):
        return self._get_update_type(obj)

    def get_user(self, obj):
        return self._get_revision_user(obj.user, obj)

    def _get_event_geometry(self, obj):
        return EventGeometry.objects.get(id=obj.object_id)

    def _get_revision_user(self, user, obj):
        if user:
            return UserDisplaySerializer().to_representation(user)

        if hasattr(obj, "event_data"):
            provenance = obj.event_data["provenance"]
            provenance_display = self._get_provenance_display(provenance)
        else:
            event = self._get_event_geometry(obj).event
            provenance = event.provenance
            provenance_display = event.get_provenance_display()

        return {
            "first_name": provenance_display,
            "last_name": "",
            "username": provenance,
        }

    def _get_provenance_display(self, provenance: str) -> str:
        provenance_display = list(filter(lambda choice: choice[0] == provenance, Event.PROVENANCE_CHOICES))

        if provenance_display and len(provenance_display[0]) == 2:
            return provenance_display[0][1]

        return ""

    def _get_update_type(self, revision):
        field_mapping = (
            ("event", "update_event"),
            ("geometry", "update_geometry"),
            ("properties", "update_properties"),
        )
        action = revision.action
        data = revision.data
        if action == "added":
            return self._get_added_action_message(revision)
        elif action == "updated":
            for key, value in field_mapping:
                if key in data:
                    return value
            return "update_event_geometry"
        return "other"

    def _get_added_action_message(self, revision):
        return f"add_{revision._meta.model_name.replace('revision', '')}"
