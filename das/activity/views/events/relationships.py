from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)
from rest_framework.response import Response

from activity.models import Event, EventRelationship
from activity.permissions import EventCategoryPermissions
from activity.serializers import EventRelationshipSerializer
from utils.drf import StandardResultsSetPagination


class EventRelationshipView(RetrieveUpdateDestroyAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventRelationshipSerializer

    def get_queryset(self):
        return EventRelationship.objects.all()

    def get_object(self):
        queryset = self.get_queryset()
        filter_kwargs = {
            "from_event_id": self.kwargs["from_event_id"],
            "to_event_id": self.kwargs["to_event_id"],
            "type__value": self.kwargs["relationship_type"],
        }
        return get_object_or_404(queryset, **filter_kwargs)

    def delete(self, request, *args, **kwargs):
        # Check for specific delete permission
        if not request.user.has_perm("activity.delete_event_relationship"):
            raise PermissionDenied("You don't have permission to delete event relationships.")

        from_event = get_object_or_404(Event.objects.all(), pk=self.kwargs["from_event_id"])
        to_event = get_object_or_404(Event.objects.all(), pk=self.kwargs["to_event_id"])
        EventRelationship.objects.remove_relationship(
            from_event=from_event,
            to_event=to_event,
            type=self.kwargs["relationship_type"],
        )
        return Response({}, status=status.HTTP_204_NO_CONTENT)


class EventRelationshipsView(ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventRelationshipSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        from_event = get_object_or_404(Event.objects.all(), pk=self.kwargs.get("from_event_id"))
        filter_kwargs = {"from_event": from_event}
        if "relationship_type" in self.kwargs:
            filter_kwargs["type__value"] = self.kwargs["relationship_type"]

        return EventRelationship.objects.filter(**filter_kwargs)

    def create(self, request, *args, **kwargs):
        relationship_type = request.data.get("type")
        from_event = get_object_or_404(Event.objects.all(), pk=self.kwargs["from_event_id"])
        to_event = get_object_or_404(Event.objects.all(), pk=request.data.get("to_event_id"))

        relation = EventRelationship.objects.add_relationship(
            from_event=from_event,
            to_event=to_event,
            type=relationship_type,
        )

        serializer = self.get_serializer(relation)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
