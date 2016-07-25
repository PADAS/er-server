from datetime import timedelta

from rest_framework import generics, status
from django.db.models import Prefetch
import rest_framework.exceptions

from activity.models import Event, EventNote, EventPhoto
from activity.serializers import EventSerializer, EventNoteSerializer,\
    EventJSONSchema, EventStateSerializer, EventPhotoSerializer
from activity.filters import EventObjectPermissionsFilter
from activity.permissions import EventObjectPermissions
from utils.drf import StandardResultsSetPagination
from utils.json import parse_bool

LAST_DAYS = timedelta(days=3)

class EventSchemaView(generics.ListCreateAPIView):
    permission_classes = (EventObjectPermissions,)
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


class EventsCountView(generics.ListAPIView):
    __doc__ = """
    Returns the count of New Events.
    """
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema
    queryset = Event.objects.all()

    def get(self, request, *args, **kwargs):
        count = Event.objects.new_count()
        data = {'count': count}
        return generics.views.Response(data)


class EventsView(generics.ListCreateAPIView):
    __doc__ = """
    Returns all events.
    Optional query-params:
    bbox, where bbox is the (west, south, east, north) lon,lat pairs.
        example: bbox=14.24, .41, 15.45, 1.66
    event_type
    state
    include_updates, true to include event updates
    include_photos, true to include photos
    include_notes, true to include notes
    page, page number
    page_size, (default is {page_size}, max is {max_page_size})
    """.format(page_size=StandardResultsSetPagination.page_size,
                    max_page_size=StandardResultsSetPagination.max_page_size)
    permission_classes = (EventObjectPermissions,)
    filter_backends = (EventObjectPermissionsFilter,)
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema

    def get_serializer_context(self):
        query_params = self.request.query_params
        context = super().get_serializer_context()
        context['include_updates'] = parse_bool(query_params.get('include_updates', True))
        context['include_notes'] = parse_bool(query_params.get('include_notes', True))
        context['include_photos'] = parse_bool(query_params.get('include_photos', True))
        return context

    def get_queryset(self):
        queryset = Event.objects.all_sort()
        query_params = self.request.query_params
        bbox = self.request.query_params.get('bbox', None)
        if bbox:
            bbox = bbox.split(',')
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")
            queryset = queryset.by_bbox(bbox, last_days=LAST_DAYS)
        state = self.request.query_params.getlist('state', None)
        if state:
            queryset = queryset.by_state(state)
        event_type = self.request.query_params.getlist('event_type', None)
        if event_type:
            queryset = queryset.by_event_type(event_type)
        queryset = queryset.prefetch_related(Prefetch('attachments'))
        queryset = queryset.prefetch_related(Prefetch('event_type'))
        queryset = queryset.prefetch_related(Prefetch('created_by_user'))
        queryset = queryset.prefetch_related(Prefetch('reported_by'))
        if parse_bool(query_params.get('include_notes', False)):
            queryset = queryset.prefetch_related(Prefetch('notes'))
        if parse_bool(query_params.get('include_photos', False)):
            queryset = queryset.prefetch_related(Prefetch('photos'))
        return queryset


class EventView(generics.RetrieveUpdateAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventSerializer
    queryset = Event.objects.all()
    lookup_field = 'id'

    def get_serializer_context(self):
        query_params = self.request.query_params
        context = super().get_serializer_context()
        context['include_updates'] = parse_bool(query_params.get('include_updates', True))
        context['include_notes'] = parse_bool(query_params.get('include_notes', True))
        context['include_photos'] = parse_bool(query_params.get('include_photos', True))
        return context


class EventStateView(generics.RetrieveUpdateAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventStateSerializer
    queryset = Event.objects.all()
    lookup_field = 'id'


class EventNotesView(generics.ListCreateAPIView):
    permission_classes = (EventObjectPermissions,)
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
    permission_classes = (EventObjectPermissions,)
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


class EventPhotosView(generics.ListCreateAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventPhotoSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        request.data['event'] = self.kwargs['id']

        # TODO: This conditional is to handle the case where a file is uploaded via XHR. Figure out why.
        if 'image' not in request.data:
            try:
                # Ajax request.
                request.data['image'] = request.stream.FILES['image']
            except KeyError:
                pass

        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['id'])

        photos = EventPhoto.objects.all().filter(event=event)
        return photos


class EventPhotoView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventPhotoSerializer

    def get_queryset(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['id'])

        photos = EventPhoto.objects.all().filter(event=event)
        return photos

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'id': self.kwargs['photo_id']}

        obj = generics.get_object_or_404(queryset, **filters)

        return obj
