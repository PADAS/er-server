from datetime import timedelta

from rest_framework.pagination import PageNumberPagination
from rest_framework import generics
import rest_framework.exceptions

from activity.models import Event, EventNote
from activity.serializers import EventSerializer, EventNoteSerializer,\
    EventJSONSchema

LAST_DAYS = timedelta(days=3)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class EventSchemaView(generics.ListCreateAPIView):
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema
    queryset = Event.objects.all()

    def get(self, request, *args, **kwargs):
        meta = self.metadata_class()
        data = meta.determine_metadata(request, self)
        return generics.views.Response(data)

    def post(self, request, *args, **kwargs):
        raise rest_framework.exceptions.MethodNotAllowed('For Schema')


class EventsView(generics.ListCreateAPIView):
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
    metadata_class = EventJSONSchema

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
        context = super().get_serializer_context()
        event = self.get_object()

        context['time'] = event.created_at
        context['coordinates'] = event.location
        return context


class EventNotesView(generics.ListCreateAPIView):
    serializer_class = EventNoteSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        request.data['event'] = self.kwargs['id']
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['id'])

        notes = EventNote.objects.all().filter(event=event)
        return notes


class EventNoteView(generics.RetrieveUpdateAPIView):
    serializer_class = EventNoteSerializer

    def get_queryset(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['id'])

        notes = EventNote.objects.all().filter(event=event)
        return notes

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'id': self.kwargs['note_id']}

        obj = generics.get_object_or_404(queryset, **filters)

        return obj
