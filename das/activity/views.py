from collections import OrderedDict
from datetime import timedelta

from rest_framework import generics, status, response
from django.db.models import Prefetch
from django.core.urlresolvers import reverse
from django.template import Template, Context

import rest_framework.exceptions
from rest_framework_extensions.etag.decorators import etag

from activity.models import Event, EventNote, EventPhoto, EventClass,\
    EventFactor, EventClassFactor, EventType, EventRelationship
from activity.serializers import EventSerializer, EventNoteSerializer,\
    EventJSONSchema, EventStateSerializer, EventPhotoSerializer,\
    EventClassSerializer, EventFactorSerializer, EventClassFactorSerializer,\
    EventTypeSerializer, EventRelationshipSerializer

from activity.alerts import get_alert_users
from activity.filters import EventObjectPermissionsFilter
from activity.permissions import EventObjectPermissions
from utils.drf import StandardResultsSetPagination
from utils.json import parse_bool, loads
import utils
from activity import schema_utils
import accounts.serializers
import accounts.models

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
        is_collection = query_params.get('is_collection', None)
        if is_collection is not None:
            queryset = queryset.by_is_collection(parse_bool(is_collection))
        return queryset


class EventTypeSchemaView(generics.ListCreateAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema
    queryset = Event.objects.all()

    def get(self, request, *args, **kwargs):
        eventtype = generics.get_object_or_404(EventType.objects.all(),
                                               value=self.kwargs['eventtype'])
        if not eventtype.schema:
            return generics.views.Response(None)

        schema_fields = schema_utils.get_replacement_fields_in_schema(eventtype.schema)

        parameters = {}
        for schema_field in schema_fields:
            if schema_field['lookup'] == 'enum':
                parameters[schema_field['tag']] = schema_utils.get_enum_choices(schema_field)
            elif schema_field['lookup'] == 'query':
                parameters[schema_field['tag']] = schema_utils.get_dynamic_choices(schema_field)
            elif schema_field['lookup'] == 'table':
                parameters[schema_field['tag']] = schema_utils.get_table_choices(schema_field)

        if len(parameters) > 0:
            template = Template(eventtype.schema)
            rendered_template = template.render(Context(parameters, autoescape=False))
            schema = loads(rendered_template, object_pairs_hook=OrderedDict)
        else:
            schema = loads(eventtype.schema, object_pairs_hook=OrderedDict)

        schema['schema']['id'] = utils.add_base_url(request, reverse('event-schema-eventtype', args=[eventtype.value, ]))

        return generics.views.Response(schema)

    def post(self, request, *args, **kwargs):
        raise rest_framework.exceptions.MethodNotAllowed('For Schema')


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
        context['include_details'] = parse_bool(query_params.get('include_details', True))
        context['include_related_events'] = parse_bool(query_params.get('include_related_events', False))
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

        is_collection = query_params.get('is_collection', None)
        if is_collection:
            queryset = queryset.by_is_collection(parse_bool(is_collection))

        event_category = query_params.getlist('event_category', None)
        if event_category:
            queryset = queryset.by_category(event_category)

        queryset = queryset.prefetch_related(Prefetch('attachments'))
        queryset = queryset.prefetch_related(Prefetch('event_type'))
        queryset = queryset.prefetch_related(Prefetch('created_by_user'))
        queryset = queryset.prefetch_related(Prefetch('reported_by'))
        queryset = queryset.prefetch_related(Prefetch('out_relationships'))

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
        context['include_related_events'] = parse_bool(query_params.get('include_related_events', True))
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


class EventRelationshipsView(generics.ListCreateAPIView):

    def perform_create(self, serializer):
        super().perform_create(serializer)

    permission_classes = (EventObjectPermissions,)
    serializer_class = EventRelationshipSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):

        type = request.data.get('type')

        from_event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['from_event_id'])

        to_event = generics.get_object_or_404(Event.objects.all(),
                                           pk=request.data.get('to_event_id'))

        relation = EventRelationship.objects.add_relationship(from_event=from_event, to_event=to_event,
                                                          type=type,)

        serializer = self.get_serializer(relation)
        headers = self.get_success_headers(serializer.data)
        return response.Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):

        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['from_event_id'])

        filter = {'from_event': event.id}

        if 'relationship_type' in self.kwargs:
            filter['type__value'] = self.kwargs['relationship_type']

        return EventRelationship.objects.filter(**filter)

class EventRelationshipView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (EventObjectPermissions,)
    serializer_class = EventRelationshipSerializer

    def get_queryset(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['from_event_id'])

        relationships = EventRelationship.objects.all().filter(from_event=event)
        return relationships

    def delete(self, request, *args, **kwargs):

        from_event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['from_event_id'])

        to_event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['to_event_id'])


        EventRelationship.objects.remove_relationship(
            from_event=from_event,
            to_event=to_event,
            type=self.kwargs['relationship_type'],
        )

        return response.Response({}, status=status.HTTP_204_NO_CONTENT)

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'from_event_id': self.kwargs['from_event_id'],
                   'to_event_id': self.kwargs['to_event_id'],
                   'type__value': self.kwargs['relationship_type']}

        obj = generics.get_object_or_404(queryset, **filters)

        return obj


class EventAlertTargetsListView(generics.ListAPIView):

    permission_classes = (EventObjectPermissions,)
    serializer_class = accounts.serializers.UserDisplaySerializer

    def get_queryset(self):
        priority = self.request.query_params.getlist('priority', None)

        priority = [int(_) for _ in priority]
        if priority:
            return get_alert_users(priority)

        return accounts.models.User.objects.none()
