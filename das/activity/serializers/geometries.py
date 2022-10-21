from rest_framework import serializers

from accounts.serializers import UserDisplaySerializer
from activity.models import EventGeometry


class EventGeometryRevisionSerializer(serializers.Serializer):
    message = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()

    def get_message(self, obj):
        return obj.get_action_display()

    def get_time(self, obj):
        return obj.revision_at.isoformat()

    def get_type(self, obj):
        return self._get_update_type(obj)

    def get_user(self, obj):
        return self._get_revision_user(obj.user, self._get_event_geometry(obj).event)

    def _get_event_geometry(self, obj):
        return EventGeometry.objects.get(id=obj.object_id)

    def _get_revision_user(self, user, event):
        if user:
            return UserDisplaySerializer().to_representation(user)
        return {
            "first_name": event.get_provenance_display(),
            "last_name": "",
            "username": event.provenance,
        }

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
