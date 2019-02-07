import platform
from collections import OrderedDict
from datetime import timedelta, datetime
import dateutil.parser as dateparser
import copy
import mimetypes
import logging
import json
import re
from django.conf import settings
from rest_framework import generics, status, response
from django.http.response import HttpResponse

from django.db.models import Prefetch, Q, F, Func
from django.urls import reverse
from django.template import Template, Context
from django.utils import timezone
from rest_framework.response import Response

import rest_framework.exceptions
from rest_framework_extensions.etag.decorators import etag
import versatileimagefield.files

from activity.models import Event, EventNote, EventClass,\
    EventFactor, EventClassFactor, EventType, EventRelationship, EventCategory, EventFile, Community,\
    EventFilter, EventSource, EventProvider
from activity.serializers import EventSerializer, EventNoteSerializer,\
    EventJSONSchema, EventStateSerializer,\
    EventClassSerializer, EventFactorSerializer, EventClassFactorSerializer,\
    EventTypeSerializer, EventRelationshipSerializer, EventCategorySerializer, EventFileSerializer, \
    EventFilterSerializer, EventSourceSerializer, EventProviderSerializer

from activity.alerts import get_alert_users
from activity.filters import EventObjectPermissionsFilter
from activity.permissions import EventCategoryPermissions, EventNotesCategoryPermissions, IsOwnerOrReadOnly, IsOwner
from rest_framework.permissions import IsAuthenticated
from utils.drf import StandardResultsSetPagination
from utils.json import parse_bool, loads
import utils
import pytz
import accounts.serializers
import accounts.models
from observations.models import Subject


from rest_framework import serializers, views, permissions
from django.views.generic.base import TemplateResponseMixin, ContextMixin

import utils.schema_utils as schema_utils

logger = logging.getLogger(__name__)

LAST_DAYS = timedelta(days=3)

USERCONTENT_FORCE_DOWNLOAD = getattr(settings, 'USERCONTENT_SETTINGS', {}).get(
    'force_download_mimetypes', set())


class EventSchemaView(generics.ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
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
    permission_classes = (EventCategoryPermissions,)
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


class EventCategoriesView(generics.ListAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventCategorySerializer

    def get_queryset(self):
        queryset = EventCategory.objects.all_sort()
        return queryset


class EventFiltersView(generics.ListCreateAPIView):
    serializer_class = EventFilterSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return EventFilter.objects.order_by('ordernum')


class EventProvidersView(generics.ListCreateAPIView):
    serializer_class = EventProviderSerializer
    pagination_class = StandardResultsSetPagination
    queryset = EventProvider.objects.all()
    permission_classes = (IsOwner,)

    def get_queryset(self):
        return EventProvider.objects.filter(owner=self.request.user, is_active=True).order_by('display')


class EventSourcesView(generics.ListCreateAPIView):

    def post(self, request, *args, **kwargs):

        request.data['eventprovider'] = kwargs['eventprovider_id']
        return super().post(request, *args, **kwargs)

    serializer_class = EventSourceSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        eventprovider_id = self.kwargs['eventprovider_id']
        return EventSource.objects.filter(eventprovider_id=eventprovider_id)


from django.shortcuts import get_object_or_404
from activity.permissions import IsEventProviderOwnerPermission


class EventSourceView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EventSourceSerializer
    permission_classes = (IsAuthenticated, IsEventProviderOwnerPermission)
    queryset = EventSource.objects.all()

    # lookup_field = 'id'

    lookup_fields = ('eventprovider_id', 'id', 'external_event_type')

    def get_object(self):
        queryset = self.get_queryset()

        filter = {}
        for field in self.lookup_fields:
            if field in self.kwargs:
                filter[field] = self.kwargs[field]

        obj = get_object_or_404(queryset, **filter)
        self.check_object_permissions(self.request, obj)
        return obj


class EventTypeSchemaView(generics.ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema
    queryset = Event.objects.all()

    def get(self, request, *args, **kwargs):
        eventtype = generics.get_object_or_404(EventType.objects.all(),
                                               value=self.kwargs['eventtype'])
        if not eventtype.schema:
            return generics.views.Response(None)

        schema_fields = schema_utils.get_replacement_fields_in_schema(
            eventtype.schema)

        parameters = {}
        for schema_field in schema_fields:
            if schema_field['lookup'] == 'enum':
                parameters[schema_field['tag']
                           ] = schema_utils.get_enum_choices(schema_field)
            elif schema_field['lookup'] == 'query':
                parameters[schema_field['tag']
                           ] = schema_utils.get_dynamic_choices(schema_field)
            elif schema_field['lookup'] == 'table':
                parameters[schema_field['tag']
                           ] = schema_utils.get_table_choices(schema_field)

        if len(parameters) > 0:
            template = Template(eventtype.schema)
            rendered_template = template.render(
                Context(parameters, autoescape=False))
            schema = loads(rendered_template, object_pairs_hook=OrderedDict)
        else:
            schema = loads(eventtype.schema, object_pairs_hook=OrderedDict)

        schema['schema']['id'] = utils.add_base_url(request, reverse(
            'event-schema-eventtype', args=[eventtype.value, ]))

        return generics.views.Response(schema)

    def post(self, request, *args, **kwargs):
        raise rest_framework.exceptions.MethodNotAllowed('For Schema')


from activity.search import get_event_search_schema


class EventFilterSchemaView(generics.RetrieveAPIView):
    def get(self, request, *args, **kwargs):

        schema = get_event_search_schema()
        schema['schema']['id'] = utils.add_base_url(
            request, reverse('eventfilter-schema-view',))

        return generics.views.Response(schema)


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
        queryset = queryset.order_by(
            'eventclass__ordernum', 'eventfactor__ordernum')

        return queryset


class EventCountView(generics.ListAPIView):
    __doc__ = """
    Returns the count of New Events.
    """
    permission_classes = (EventCategoryPermissions,)
    queryset = Event.objects.all()

    def get(self, request, *args, **kwargs):

        queryset = Event.objects.new()

        event_categories = self.request.query_params.getlist(
            'event_category', None)
        if event_categories is None or len(event_categories) == 0:
            event_categories = EventCategory.objects.values_list(
                'value').distinct()
            event_categories = [x[0] for x in event_categories]

        allowed_event_categories = []
        for event_category in event_categories:
            permission_name = 'activity.{0}_read'.format(event_category)
            if self.request.user.has_perm(permission_name):
                allowed_event_categories.append(event_category)

        if len(allowed_event_categories) > 0:
            queryset = queryset.by_category(allowed_event_categories)
        else:
            raise rest_framework.exceptions.PermissionDenied

        data = {'count': queryset.count()}
        return generics.views.Response(data)


class EventsExportView(views.APIView, TemplateResponseMixin, ContextMixin, ):

    permission_classes = (EventCategoryPermissions,)

    def get_event_export_list(self):
        event_export_data = []

        renderer = schema_utils.get_schema_renderer_method()

        current_event_type_data = {'id': None}
        current_tz_name = timezone.get_current_timezone_name()
        current_tz = pytz.timezone(current_tz_name)
        current_date = datetime.utcnow().astimezone(current_tz)
        tz_difference = current_date.utcoffset().total_seconds() / 60 / 60
        tz_offset = 'GMT' + ('+' if tz_difference >= 0 else '') + str(
            int(tz_difference)) + ':' + str(
            int((tz_difference - int(tz_difference)) * 60))
        reported_at = 'Reported At ({})'.format(tz_offset)
        default_headers = [
                        'Report Type', 'Report Type Internal Value', 'Report Id', 'Title',
                        'Priority', 'Priority Internal Value', 'Status', 'Reported By',
                        'Reported By Internal Value', reported_at, 'Latitude', 'Longitude', 
                        'Number of Notes', 'Notes', 'Number of Related Subjects', 
                        'Collection Report Id', 'CUSTOM FIELDS BEGIN HERE'
                        ]
        custom_headers = []
        combined_headers = []

        for event in self.get_queryset():
            if event.event_type_id != current_event_type_data['id']:
                event_type = EventType.objects.get(id=event.event_type_id)

                current_event_type_data = {
                    'id': event_type.id,
                    'display': event_type.display,
                    'value': event_type.value,
                    'events': [],
                    'headers': copy.deepcopy(default_headers)
                }

                try:
                    current_schema = renderer(event.event_type.schema)
                    current_schema_order = schema_utils.definition_key_order_as_dict(
                        renderer(event.event_type.schema))

                    for key, order in current_schema_order.items():
                        if not isinstance(key, int):
                            display_value = schema_utils.get_display_value_header_for_key(
                                current_schema, key)
                            current_event_type_data['headers'].append(
                                self.escape_string(key))
                            current_event_type_data['headers'].append(
                                self.escape_string(display_value))

                            if display_value not in custom_headers:
                                custom_headers.append(display_value)
                except json.JSONDecodeError:
                    # Event type does not have schema, which is weird but not
                    # _technically_ invalid
                    current_schema = None
                    current_schema_order = {}

                event_export_data.append(current_event_type_data)

            # First, get the event details (schema data) in the correct order
            # for the headers above
            details = schema_utils.get_details_and_display_values(event,
                                                                  current_schema)

            schema_data = OrderedDict()
            for key, order in current_schema_order.items():
                item_display_name = schema_utils.get_display_value_header_for_key(
                    current_schema, key)
                # schema_data[key] = self.escape_string(details.get(key, ''))
                # schema_data[item_display_name] = self.escape_string(
                #     details.get(item_display_name, ''))
                schema_data[item_display_name] = details.get(item_display_name, '')

            parent_event = Event.objects.filter(
                out_relationship__to_event=event,
                out_relationship__type__value='contains').first()
            if parent_event is not None:
                parent_event = str(parent_event.serial_number)
            else:
                parent_event = ''

            # Now assemble the data we want to write to the csv
            event_time = event.time.astimezone(current_tz)
            event_data = {
                'serial': event.serial_number,
                'event_type': event_type.display,
                'event_type_internal': event_type.value,
                'title': self.escape_string(event.title),
                'priority': event.priority_label,
                'priority_internal': event.priority,
                'reported_at': event_time.strftime('%Y-%m-%d %H:%M'),
                'lat': event.location.y if event.location is not None else '',
                'lon': event.location.x if event.location is not None else '',
                'num_notes': event.notes.count(),
                'notes': '\n'.join([note.text for note in event.notes.all()]),
                'num_attach': event.related_subjects.count(),
                'parent_id': parent_event,
                'status': 'Resolved' if event.state == Event.SC_RESOLVED else 'Active',
                'details': schema_data
            }

            # Reported by depends on what sort of entity reported the event
            if event.reported_by is None:
                event_data['reported_by'] = ''
                event_data['reported_by_internal'] = ''
            elif isinstance(event.reported_by, Subject):
                event_data['reported_by'] = self.escape_string(
                    event.reported_by.name)
                event_data['reported_by_internal'] = event.reported_by.id
            elif isinstance(event.reported_by, Community):
                event_data['reported_by'] = event.reported_by.name
                event_data['reported_by_internal'] = event.reported_by.name
            else:
                full_name = '{0} {1}'.format(
                    event.reported_by.first_name, event.reported_by.last_name)
                event_data['reported_by'] = self.escape_string(full_name)
                event_data['reported_by_internal'] = event.reported_by.username

            current_event_type_data['events'].append(event_data)

        if not combined_headers:
            combined_headers.extend(default_headers)
            combined_headers.extend(custom_headers)
        return {
            'event_export_data': event_export_data,
            'combined_headers': [header.replace(' ', '_') for header in combined_headers],
            'custom_headers': custom_headers
            }

    def escape_string(self, string):
        if not isinstance(string, str):
            return string
        string = string.replace('"', '""')
        return '"' + string + '"'

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def render_to_response(self, context, **response_kwargs):

        response = super().render_to_response(context, **response_kwargs)
        response['Content-Disposition'] = 'attachment; filename={}'.format(
            context['report_filename'])
        response['x-das-download-filename'] = context['report_filename']
        return response

    def get_context_data(self, **kwargs):
        REPORT_TIME_FORMAT = '%-d %B %Y %Z' if platform.system().lower() != 'windows' else '%#d %B %Y %Z'
        current_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = current_tz.localize(datetime.utcnow())
        context = {
            'report_filename': 'Event Export {}.csv'.format(timestamp.strftime('%Y-%m-%d')),
            'report_time': timestamp.strftime(REPORT_TIME_FORMAT),
            'event_types': self.get_event_export_list()
        }

        return context

    def get_queryset(self):

        # TODO: Update to allow passing last_days constraint.

        queryset = Event.objects.all()

        query_params = self.request.query_params
        bbox = query_params.get('bbox', None)
        if bbox:
            bbox = bbox.split(',')
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")

            queryset = queryset.by_bbox(bbox)

        event_filter = self.request.query_params.get('filter', None)
        if event_filter:
            try:
                event_filter = json.loads(event_filter)
                queryset = queryset.by_event_filter(event_filter)
            except json.JSONDecodeError:
                logger.exception(
                    'Invalid filter expression. filter=%s', event_filter)
                raise

        state = query_params.getlist('state', None)
        if state:
            queryset = queryset.by_state(state)

        return queryset.order_by('event_type_id')


class EventsView(generics.ListCreateAPIView):
    __doc__ = """
    Returns all events.
    Optional query-params:
    bbox, where bbox is the (west, south, east, north) lon,lat pairs.
        example: bbox=14.24, .41, 15.45, 1.66
    event_type
    state
    include_updates, true to include event updates
    include_notes, true to include notes
    page, page number
    page_size, (default is {page_size}, max is {max_page_size})
    """.format(page_size=StandardResultsSetPagination.page_size,
               max_page_size=StandardResultsSetPagination.max_page_size)
    permission_classes = (EventCategoryPermissions,)
    filter_backends = (EventObjectPermissionsFilter,)
    serializer_class = EventSerializer
    pagination_class = StandardResultsSetPagination
    metadata_class = EventJSONSchema

    def get_serializer_context(self):

        query_params = self.request.query_params \
            if self.request and hasattr(self.request, 'query_params') else {}

        context = super().get_serializer_context()
        request = context['request']
        context['include_updates'] = parse_bool(
            query_params.get('include_updates', True))

        context['include_details'] = parse_bool(
            query_params.get('include_details', True))
        context['include_files'] = parse_bool(
            query_params.get('include_files', True))

        # if this is a POST, returned any contained events
        try:
            include_for_posts = request._request.method == 'POST'
        except AttributeError:
            include_for_posts = False

        context['include_related_events'] = parse_bool(query_params.get('include_related_events',
                                                                        include_for_posts))
        context['include_notes'] = parse_bool(
            query_params.get('include_notes', include_for_posts))

        try:
            context['eventsource_id'] = request.data.get('eventsource_id')
        except AttributeError:
            pass

        return context

    def get_queryset(self):

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

        event_filter = self.request.query_params.get('filter', None)
        if event_filter:
            try:
                event_filter = json.loads(event_filter)
                queryset = queryset.by_event_filter(event_filter)
            except json.JSONDecodeError:
                logger.exception(
                    'Invalid filter expression. filter=%s', event_filter)
                raise

        is_collection = query_params.get('is_collection', None)
        exclude_contained = query_params.get('exclude_contained', None)
        if is_collection and exclude_contained:
            raise ValueError(
                'invalid use of is_collection and exclude_contained in the same call')

        if is_collection:
            queryset = queryset.by_is_collection(parse_bool(is_collection))
        if exclude_contained:
            queryset = queryset.by_exclude_contained(
                parse_bool(exclude_contained))

        updated_since = query_params.get('updated_since', None)

        if updated_since:
            try:
                updated_since = dateparser.parse(updated_since)
                queryset = queryset.updated_since(updated_since)
            except ValueError:
                raise ValueError(f"Invalid value for 'updated_since' = '{updated_since}'")

        event_categories = query_params.getlist('event_category', None)
        if event_categories is None or len(event_categories) == 0:
            event_categories = EventCategory.objects.values_list(
                'value').distinct()
            event_categories = [x[0] for x in event_categories]

        allowed_event_categories = []
        for event_category in event_categories:
            permission_name = 'activity.{0}_read'.format(event_category)
            if self.request.user.has_perm(permission_name):
                allowed_event_categories.append(event_category)

        if len(allowed_event_categories) > 0:
            queryset = queryset.by_category(allowed_event_categories)
        else:
            raise rest_framework.exceptions.PermissionDenied

        queryset = queryset.prefetch_related(Prefetch('related_subjects'))
        queryset = queryset.prefetch_related(Prefetch('event_type'))
        queryset = queryset.prefetch_related(Prefetch('created_by_user'))
        queryset = queryset.prefetch_related(Prefetch('reported_by'))
        queryset = queryset.prefetch_related(Prefetch('out_relationships'))

        if parse_bool(query_params.get('include_notes', False)):
            queryset = queryset.prefetch_related(Prefetch('notes'))
        if parse_bool(query_params.get('include_files', False)):
            queryset = queryset.prefetch_related(Prefetch('files'))

        return queryset


def calculate_event_etag(view_instance, view_method, request, *args, **kwargs):
    instance = view_instance.get_object()
    return str(hash(instance.updated_at))


class EventView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventSerializer

    lookup_field = 'id'

    @etag(etag_func=calculate_event_etag)
    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj:
            self.check_object_permissions(self.request, obj)
        return super().get(request, *args, **kwargs)

    def get_serializer_context(self):

        query_params = self.request.query_params \
            if self.request and hasattr(self.request, 'query_params') else {}

        context = super().get_serializer_context()

        context['include_updates'] = parse_bool(
            query_params.get('include_updates', True))
        context['include_notes'] = parse_bool(
            query_params.get('include_notes', True))
        context['include_files'] = parse_bool(
            query_params.get('include_files', True))
        context['include_related_events'] = parse_bool(
            query_params.get('include_related_events', True))
        return context

    def get_queryset(self):
        queryset = Event.objects.all()

        event_filter = self.request.query_params.get('filter', None)
        if event_filter:
            try:
                event_filter = json.loads(event_filter)
                return queryset.by_event_filter(event_filter)
            except:
                logger.warning('Invalid filter expression %s', event_filter)
        return queryset


class EventStateView(generics.RetrieveUpdateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventStateSerializer
    queryset = Event.objects.all()
    lookup_field = 'id'


class EventNotesView(generics.ListCreateAPIView):
    permission_classes = (EventNotesCategoryPermissions,)
    serializer_class = EventNoteSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        request.data['event'] = self.kwargs['id']
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        event = self.get_event()

        notes = EventNote.objects.all().filter(event=event)
        return notes

    def get_event(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['id'])
        return event


class EventNoteView(generics.RetrieveUpdateAPIView):
    permission_classes = (EventNotesCategoryPermissions,)
    serializer_class = EventNoteSerializer

    def get_queryset(self):
        event = self.get_event()

        notes = EventNote.objects.all().filter(event=event)
        return notes

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'id': self.kwargs['note_id']}

        obj = generics.get_object_or_404(queryset, **filters)

        return obj

    def get_event(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['id'])
        return event


def resolve_first(dicts, keys):
    for d in dicts:
        for k in keys:
            if k in d:
                return d[k]
                break


from usercontent.serializers import UserContentSerializer


class EventFilesView(generics.ListCreateAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventFileSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):

        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['id'])

        # TODO: This conditional is to handle the case where a file is uploaded
        # via XHR. Figure out why.
        if 'filecontent.file' not in request.data:
            try:
                # Ajax request.
                request.data['filecontent.file'] = request.stream.FILES['filecontent.file']
            except KeyError:
                pass

        this_data = copy.copy(request.data)
        this_data['event'] = event.id

        this_data['usercontent.file'] = this_data['filecontent.file']

        serializer = self.get_serializer(data=this_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['id'])

        return event.files.all()


from usercontent.serializers import get_stored_filename


class EventFileView(generics.RetrieveUpdateDestroyAPIView):

    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventFileSerializer

    def get_queryset(self):
        event = generics.get_object_or_404(Event.objects.all(),
                                           pk=self.kwargs['event_id'])

        qs = EventFile.objects.all().filter(event=event)
        return qs

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'id': self.kwargs['filecontent_id']}

        obj = generics.get_object_or_404(queryset, **filters)
        return obj

    def get(self, request, *args, **kwargs):

        # if request.GET.get('data', 'false').lower() == 'true':
        if self.kwargs.get('filename', None) == 'meta-data':
            return super().get(request, *args, **kwargs)

        instance = self.get_object()

        desired_image_size = self.kwargs.get('image_size', None)
        content_type, encoding = mimetypes.guess_type(
            instance.usercontent.filename)

        if content_type in USERCONTENT_FORCE_DOWNLOAD:
            content_type = 'application/octet-stream'

        if isinstance(instance.usercontent.file, (versatileimagefield.files.VersatileImageFieldFile,)):
            filename = get_stored_filename(instance.usercontent.file, rendition_set='default',
                                           rendition_key=desired_image_size)
            try:
                response_file = instance.usercontent.file.field.storage.open(
                    filename)
            except OSError as oe:
                logger.warning(
                    'Failed attempt to open file %s. Will default to original file version.', filename)
                response_file = instance.usercontent.file

            response = HttpResponse(response_file, content_type=content_type)
        else:
            response = HttpResponse(
                instance.usercontent.file, content_type=content_type)
            response['Content-Disposition'] = 'attachment; filename=%s' % instance.usercontent.filename

        return response


class EventRelationshipsView(generics.ListCreateAPIView):

    def perform_create(self, serializer):
        super().perform_create(serializer)

    permission_classes = (EventCategoryPermissions,)
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
    permission_classes = (EventCategoryPermissions,)
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

    permission_classes = (EventCategoryPermissions,)
    serializer_class = accounts.serializers.UserDisplaySerializer

    def get_queryset(self):
        priority = self.request.query_params.getlist('priority', None)

        priority = [int(_) for _ in priority]
        if priority:
            return get_alert_users(priority)

        return accounts.models.User.objects.none()
