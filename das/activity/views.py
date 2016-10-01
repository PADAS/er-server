from datetime import timedelta

from rest_framework import generics, status
from django.db.models import Prefetch
from django.core.urlresolvers import reverse
from django.template import Template, Context
from django.template.base import VariableNode

from core.models import Choice

import rest_framework.exceptions
from rest_framework_extensions.etag.decorators import etag

from activity.models import Event, EventNote, EventPhoto, EventClass,\
    EventFactor, EventClassFactor, EventType
from activity.serializers import EventSerializer, EventNoteSerializer,\
    EventJSONSchema, EventStateSerializer, EventPhotoSerializer,\
    EventClassSerializer, EventFactorSerializer, EventClassFactorSerializer,\
    EventTypeSerializer
from activity.filters import EventObjectPermissionsFilter
from activity.permissions import EventObjectPermissions
from utils.drf import StandardResultsSetPagination
from utils.json import parse_bool, loads, dumps
import utils

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


class EventTypesView(generics.ListAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventTypeSerializer

    def get_queryset(self):
        query_params = self.request.query_params
        queryset = EventType.objects.all_sort()

        category = query_params.getlist('category', None)
        if category:
            queryset = queryset.by_category(category)
        return queryset


class EventTypeSchemaView(generics.ListCreateAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema
    queryset = Event.objects.all()

    def get(self, request, *args, **kwargs):
        value = kwargs['eventtype']
        eventtype = generics.get_object_or_404(EventType.objects.all(),
                                               value=self.kwargs['eventtype'])
        schema = None
        if eventtype.schema:
            template = Template(eventtype.schema)
            dynamic_fields = self._generate_render_field_list(template)

            # If there are dynamic fields in this schema, we need to
            # generate values and render it before it's usable
            if len(dynamic_fields) > 0:
                parameters = {}
                for dynamic_field in dynamic_fields:
                    parameters[dynamic_field] = self._generate_choice_list(
                        dynamic_field)

                rendered_template = template.render(Context(parameters,
                                                            autoescape=False))
                schema = loads(rendered_template)

            # If there are no dynamic fields, then it's super simple
            else:
                schema = loads(eventtype.schema)

            # 'activity/events/schema/eventtype/{0}'.format(eventtype.value)
            url = utils.add_base_url(request, reverse('event-schema-eventtype',
                                     args=[eventtype.value, ]))
            schema['schema']['id'] = url

        return generics.views.Response(schema)

    def post(self, request, *args, **kwargs):
        raise rest_framework.exceptions.MethodNotAllowed('For Schema')

    def _generate_render_field_list(self, template):
        render_fields = []
        for node in template.nodelist:
            if type(node) is VariableNode:
                render_fields.append(node.token.contents)

        return render_fields

    def _generate_choice_list(self, field_name):
        field_details = field_name.split('___')

        if len(field_details) == 1:
            choices = Choice.objects.filter(model='activity.event',
                                            field=field_name)
        elif len(field_details) == 2:
            choices = Choice.objects.filter(model='activity.event',
                                            field=field_details[0])
        else:
            raise NameError('Incorrect event render tag: ' + field_name)

        options = {}
        for choice in choices:
            options[choice.value] = choice.display

        if len(field_details) == 2 and field_details[1] == 'names':
            return dumps(options)

        return dumps(list(options.keys()))


class EventClassesView(generics.ListAPIView):
    serializer_class = EventClassSerializer
    queryset = EventClass.objects.all().order_by('ordernum')


class EventFactorsView(generics.ListAPIView):
    serializer_class = EventFactorSerializer
    queryset = EventFactor.objects.all().order_by('ordernum')


class EventClassFactorsView(generics.ListAPIView):
    serializer_class = EventClassFactorSerializer
    def get_queryset(self):
        queryset = EventClassFactor.objects.all()
        queryset = queryset.order_by('eventclass__ordernum', 'eventfactor__ordernum')

        return queryset


class EventCountView(generics.ListAPIView):
    __doc__ = """
    Returns the count of New Events.
    """
    permission_classes = (EventObjectPermissions,)
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

        # TODO: Update to allow passing last_days constraint.
        queryset = Event.objects.all_sort()
        query_params = self.request.query_params
        bbox = query_params.get('bbox', None)
        if bbox:
            bbox = bbox.split(',')
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")

            queryset = queryset.by_bbox(bbox)
        state = query_params.getlist('state', None)
        if state:
            queryset = queryset.by_state(state)

        event_type = query_params.getlist('event_type', None)
        if event_type:
            queryset = queryset.by_event_type(event_type)

        event_category = query_params.getlist('event_category', None)
        if event_category:
            queryset = queryset.by_category(event_category)

        queryset = queryset.prefetch_related(Prefetch('attachments'))
        queryset = queryset.prefetch_related(Prefetch('event_type'))
        queryset = queryset.prefetch_related(Prefetch('created_by_user'))
        queryset = queryset.prefetch_related(Prefetch('reported_by'))
        if parse_bool(query_params.get('include_notes', False)):
            queryset = queryset.prefetch_related(Prefetch('notes'))
        if parse_bool(query_params.get('include_photos', False)):
            queryset = queryset.prefetch_related(Prefetch('photos'))
        return queryset


def calculate_event_etag(view_instance, view_method, request, *args, **kwargs):
    instance = view_instance.get_object()
    return str(hash(instance.updated_at))


class EventView(generics.RetrieveUpdateAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventSerializer
    queryset = Event.objects.all()
    lookup_field = 'id'

    @etag(etag_func=calculate_event_etag)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

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
