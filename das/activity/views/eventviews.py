from datetime import timedelta

from rest_framework.pagination import PageNumberPagination
from rest_framework import generics

from activity.models import Event, EventNote
from activity.serializers import EventSerializer

LAST_DAYS = timedelta(days=3)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class EventsView(generics.ListCreateAPIView):
    def perform_create(self, serializer):
        serializer.save(created_by_user=self.request.user)

    __doc__ = """
    Returns all events.
    Optional query-params:
    bbox, where bbox is the (west, south, east, north) lon,lat pairs.
        example: bbox=14.24, .41, 15.45, 1.66
    page, page number
    page_size, (default is {page_size}, max is {max_page_size})
    """.format(page_size=StandardResultsSetPagination.page_size,
                    max_page_size=StandardResultsSetPagination.max_page_size)

    serializer_class = EventSerializer

    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Event.objects.all().order_by('-created_at')
        bbox = self.request.query_params.get('bbox', None)
        if bbox:
            bbox = bbox.split(',')
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")
            queryset = Event.objects.by_bbox(bbox, last_days=LAST_DAYS).order_by('-created_at')
        return queryset


class EventView(generics.RetrieveUpdateAPIView):
    serializer_class = EventSerializer
    queryset = Event.objects.all()
    lookup_field = 'id'

    def get_serializer_context(self):
        context = {}
        event = self.get_object()

        context['time'] = event.created_at
        context['coordinates'] = event.location
        context['request'] = self.request
        return context


class EventNoteView(generics.RetrieveUpdateAPIView):
    serializer_class = EventSerializer
    queryset = EventNote.objects.all()
    lookup_field = 'id'

    def get_serializer_context(self):
        context = {}
        note = self.get_object()
        context['time'] = note.created_at
        context['request'] = self.request
        return context
