from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)
from rest_framework.permissions import IsAuthenticated

from activity.models import EventSource
from activity.permissions import IsEventProviderOwnerPermission
from activity.serializers import EventSourceSerializer
from utils.drf import StandardResultsSetPagination


class EventSourceView(RetrieveUpdateDestroyAPIView):
    serializer_class = EventSourceSerializer
    permission_classes = (IsAuthenticated, IsEventProviderOwnerPermission)
    queryset = EventSource.objects.all()

    lookup_fields = ("eventprovider_id", "id", "external_event_type")

    def get_object(self):
        queryset = self.get_queryset()

        filter = {}
        for field in self.lookup_fields:
            if field in self.kwargs:
                filter[field] = self.kwargs[field]

        obj = get_object_or_404(queryset, **filter)
        self.check_object_permissions(self.request, obj)
        return obj


class EventSourcesView(ListCreateAPIView):
    def post(self, request, *args, **kwargs):
        request.data["eventprovider"] = kwargs["eventprovider_id"]
        return super().post(request, *args, **kwargs)

    serializer_class = EventSourceSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        eventprovider_id = self.kwargs["eventprovider_id"]
        return EventSource.objects.filter(eventprovider_id=eventprovider_id)
