from activity.models import Event, EventCategory
from core.serializers import GenericRelatedField


class ReportedByRelatedField(GenericRelatedField):
    def get_field_mapping(self, label="ReportedBy"):
        return super().get_field_mapping(label)

    def check_has_event_category_permission(self):
        # Checks if the user has any event-category permission.
        event_categories = EventCategory.objects.values_list("value").distinct()
        event_categories = [ec[0] for ec in event_categories]
        actions = ("create", "update", "read", "delete")
        request = self.context.get("request")

        for event_category in event_categories:
            permission_name = [f"activity.{event_category}_{action}" for action in actions]
            for perm in permission_name:
                if request.user.has_perm(perm):
                    return True

    def get_object_queryset(self):
        if not self.check_has_event_category_permission():
            return False

        request = self.context.get("request")

        for p in Event.PROVENANCE_CHOICES:
            provenance = p[0]
            values = list(Event.objects.get_reported_by_for_provenance(provenance, request.user))
            if values:
                yield provenance, values
