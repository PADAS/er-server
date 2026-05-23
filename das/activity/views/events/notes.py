from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)

from activity.models import Event, EventNote
from activity.permissions import EventNotesPermissions
from activity.serializers import EventNoteSerializer
from utils.drf import StandardResultsSetPagination


class EventNoteView(RetrieveUpdateDestroyAPIView):
    permission_classes = (EventNotesPermissions,)
    serializer_class = EventNoteSerializer

    def get_queryset(self):
        event = self.get_event()

        notes = EventNote.objects.all().filter(event=event)
        return notes

    def get_object(self):
        queryset = self.get_queryset()
        filters = {"id": self.kwargs["note_id"]}

        obj = get_object_or_404(queryset, **filters)

        return obj

    def get_event(self):
        event = get_object_or_404(Event.objects.all(), pk=self.kwargs.get("id"))
        return event


class EventNotesView(ListCreateAPIView):
    permission_classes = (EventNotesPermissions,)
    serializer_class = EventNoteSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        if hasattr(request.data, "_mutable"):
            request.data._mutable = True
        request.data["event"] = self.kwargs["id"]
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        if self.request.user.is_anonymous:
            serializer.save(created_by_user=None)
        else:
            super().perform_create(serializer)

    def get_queryset(self):
        event = self.get_event()

        notes = EventNote.objects.all().filter(event=event)
        return notes

    def get_event(self):
        event = get_object_or_404(Event.objects.all(), pk=self.kwargs.get("id"))
        return event
