import copy
import csv
import json
import logging
import mimetypes
import platform
from collections import OrderedDict
from datetime import timedelta, datetime

import dateutil.parser as dateparser
import pytz
import rest_framework.exceptions
import versatileimagefield.files
from django.conf import settings
from django.contrib.postgres.aggregates import StringAgg, ArrayAgg
from django.db import transaction
from django.db.models import CharField, Value
from django.db.models import Prefetch, F, Count
from django.db.models.functions import Concat, Cast
from django.http import Http404
from django.http.response import HttpResponse
from django.template import Template, Context
from django.urls import reverse
from django.utils import timezone
from django.views.generic.base import TemplateResponseMixin, ContextMixin
from rest_framework import generics, status, response
from rest_framework import views
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_extensions.etag.decorators import etag

import accounts.models
import accounts.serializers
import utils
import utils.schema_utils as schema_utils
from accounts.models import User
from activity.filters import EventObjectPermissionsFilter
from activity.models import Event, EventNote, EventClass, \
    EventFactor, EventClassFactor, EventType, EventRelationship, EventCategory, \
    EventFile, Community, StateFilters, \
    EventFilter, EventSource, EventProvider, PatrolType, Patrol, PatrolSegment, PatrolNote, PatrolFile, \
    EventRelatedSegments
from activity.permissions import EventCategoryPermissions, \
    EventNotesCategoryPermissions, IsOwner
from activity.serializers import EventSerializer, EventNoteSerializer, \
    EventJSONSchema, EventStateSerializer, \
    EventClassSerializer, EventFactorSerializer, EventClassFactorSerializer, \
    EventTypeSerializer, EventRelationshipSerializer, EventCategorySerializer, \
    EventFileSerializer, \
    EventFilterSerializer, EventSourceSerializer, EventProviderSerializer, \
    EventGeoJsonSerializer, \
    PatrolTypeSerializer, EventRelatedSegmentSerializer
from activity.serializers.patrol_serializers import PatrolSerializer, PatrolSegmentSerializer, PatrolNoteSerializer, PatrolFileSerializer
from choices.models import Choice
from observations.models import Subject
from utils.drf import StandardResultsSetPagination, \
    StandardResultsSetGeoJsonPagination
from utils.json import parse_bool, loads, ExtendedGEOJSONRenderer
from das_server.views import CustomSchema

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
        queryset = queryset.filter(category__is_active=True)

        category = query_params.getlist('category', None)
        if category:
            queryset = queryset.by_category(category)
        else:
            allowed_categories = []
            event_categories = EventCategory.objects.values_list(
                'value').distinct()
            event_categories = [ec[0] for ec in event_categories]
            actions = ('create', 'update', 'read', 'delete')

            for event_category in event_categories:
                permission_name = [
                    f'activity.{event_category}_{action}' for action in actions]
                if any([self.request.user.has_perm(perm) for perm in permission_name]):
                    allowed_categories.append(event_category)

            if allowed_categories:
                queryset = queryset.by_category(allowed_categories)
            elif query_params.get('is_collection', None) is None:
                return queryset.none()

        is_collection = query_params.get('is_collection', None)
        if is_collection is not None:
            queryset = queryset.by_is_collection(parse_bool(is_collection))
        return queryset


class EventCategoriesView(generics.ListAPIView):
    permission_classes = (EventCategoryPermissions,)
    serializer_class = EventCategorySerializer

    def get_queryset(self):
        queryset = EventCategory.objects.all_sort()
        queryset = queryset.filter(is_active=True)
        for q in queryset:
            actions = ('create', 'update', 'read', 'delete')
            permission_name = [
                f'activity.{q.value}_{action}' for action in actions]
            if not any([self.request.user.has_perm(perm) for perm in permission_name]):
                queryset = queryset.exclude(id=q.id)
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
        return EventProvider.objects.filter(owner=self.request.user,
                                            is_active=True).order_by('display')


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
                                               value__iexact=self.kwargs['eventtype'])

        if not eventtype.schema:
            return generics.views.Response(None)

        definition_format = self.request.query_params.get(
            'definition', None)

        schema_fields = schema_utils.get_replacement_fields_in_schema(
            eventtype.schema)

        parameters = {}
        enumImages_vals = {}
        for schema_field in schema_fields:
            if schema_field['lookup'] == 'enum':
                icon_vals = schema_utils.get_enumImage_values(schema_field)
                if icon_vals:
                    enumImages_vals[schema_field['field']] = icon_vals
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

        if 'schema' not in schema:
            return generics.views.Response(None)

        schema['schema']['id'] = utils.add_base_url(request, reverse(
            'event-schema-eventtype', args=[eventtype.value, ]))
        schema['schema']['icon_id'] = eventtype.icon_id
        schema['schema']['image_url'] = utils.add_base_url(
            request, eventtype.image_url)

        field_schema = schema_utils.map_schema(eventtype.schema, schema)
        for key, value in field_schema.items():
            inactive_choices = []
            obj = Choice.objects.filter(
                is_active=False, field=value['field_name'])
            for o in obj:
                inactive_choices.append(o.value)
            if inactive_choices:
                schema['schema']['properties'][key]["inactive" +
                                                    "_" + value['lookup']] = inactive_choices

        for value in schema_utils.get_values_titlemap(eventtype.schema):
            inactive_choices = []
            obj = Choice.objects.filter(is_active=False, field=value)
            for o in obj:
                inactive_choices.append(o.value)
            if inactive_choices:

                for key in schema['definition']:
                    if isinstance(key, OrderedDict):
                        items = key.get('items')

                        tmap_values = [(i, i['titleMap']) for i in items if isinstance(i, OrderedDict)
                                       and i.get('titleMap')] if items else None

                        # TODO: Consider the truthiness of tmap_values here,
                        # for the case where it is set to [].
                        if tmap_values:
                            for item, tmap in tmap_values:
                                for tm in tmap:
                                    if tm.get('value') in inactive_choices:
                                        item['inactive_titleMap'] = inactive_choices

                        elif key.get('titleMap'):
                            for title_map_elem in key.get('titleMap'):
                                if title_map_elem.get('value') in inactive_choices:
                                    key['inactive_titleMap'] = inactive_choices

        for key, value in field_schema.items():
            for o, vals in enumImages_vals.items():
                if value['field_name'] == o:
                    schema['schema']['properties'][key]['enumImages'] = vals

        # Apply definition filter
        try:
            schema = schema_utils.filter_schema_definition(
                schema, definition_format)
        except ValueError as ex:
            return Response(str(ex), status=status.HTTP_400_BAD_REQUEST)

        return generics.views.Response(schema)

    def post(self, request, *args, **kwargs):
        raise rest_framework.exceptions.MethodNotAllowed('For Schema')


from activity.search import get_event_search_schema


class EventFilterSchemaView(generics.RetrieveAPIView):
    def get(self, request, *args, **kwargs):
        schema = get_event_search_schema()
        schema['schema']['id'] = utils.add_base_url(
            request, reverse('eventfilter-schema-view', ))

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
            queryset = queryset.none()

        data = {'count': queryset.count()}
        return generics.views.Response(data)


def generate_reported_by_lookup():
    user_qs = User.objects.all() \
        .annotate(internal_id=Cast('id', CharField()), value=F('username'),
                  kind=Value('user', output_field=CharField()),
                  display_value=Concat('first_name', Value(' '), 'last_name')) \
        .values_list('internal_id', 'value', 'kind', 'display_value')
    community_qs = Community.objects.all() \
        .annotate(internal_id=Cast('id', CharField()), value=F('name'),
                  kind=Value('community', output_field=CharField()),
                  display_value=F('name')) \
        .values_list('internal_id', 'value', 'kind', 'display_value')
    reported_by_qs = Subject.objects.all() \
        .annotate(internal_id=Cast('id', CharField()),
                  value=Cast('id', CharField()),
                  kind=Value('subject', output_field=CharField()),
                  display_value=F('name')) \
        .values_list('internal_id', 'value', 'kind', 'display_value')

    reported_by_list = reported_by_qs.union(user_qs, community_qs)

    reported_by_map = dict(
        (x[0], {'value': x[1], 'kind': x[2], 'display': x[3]}) for x in
        reported_by_list)
    return reported_by_map


def generate_event_type_cache():
    event_types = EventType.objects.all().values('id', 'value', 'display', 'schema')
    event_types_map = dict(
        (event_type['id'], event_type) for event_type in event_types
    )
    return event_types_map


class EventsExportView(views.APIView):
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
            'Priority', 'Priority Internal Value', 'Report Status', 'Reported By',
            reported_at, 'Latitude', 'Longitude',
            'Number of Notes', 'Notes', 'Number of Related Subjects',
            'Collection Report IDs', 'CUSTOM FIELDS BEGIN HERE'
        ]
        custom_headers = []
        combined_headers = []

        reported_by_map = generate_reported_by_lookup()

        event_type_map = generate_event_type_cache()

        for event in self.get_queryset() \
            .annotate(notes_count=Count('note')) \
            .annotate(full_notes=StringAgg('note__text', delimiter='\n')) \
            .annotate(related_subjects_count=Count('related_subjects')) \
            .annotate(parent_event_serial_numbers=ArrayAgg('in_relationship__from_event__serial_number', distinct=True)) \
            .values('id', 'serial_number', 'priority', 'state',
                    'title', 'event_type_id', 'event_details__data',
                    'notes_count', 'full_notes', 'parent_event_serial_numbers',
                    'location', 'event_time', 'reported_by_id',
                    'related_subjects_count'):

            if event['event_type_id'] != current_event_type_data['id']:
                event_type = event_type_map[event['event_type_id']]

                current_event_type_data = {
                    'id': event['event_type_id'],
                    'display': event_type['display'],
                    'value': event_type['value'],
                    'events': [],
                    'headers': copy.deepcopy(default_headers)
                }

                try:
                    current_schema = renderer(event_type['schema'])
                    current_schema_order = \
                        schema_utils.property_keys_order_as_dict(
                            current_schema)

                    for key, order in current_schema_order.items():
                        if not isinstance(key, int):
                            display_value = schema_utils.get_display_value_header_for_key(
                                current_schema, key)
                            current_event_type_data['headers'].append(
                                self.escape_string(key))
                            current_event_type_data['headers'].append(
                                self.escape_string(display_value))

                            if self.value_cols and key not in custom_headers:
                                custom_headers.append(key)

                            if self.display_cols:
                                column_name = schema_utils.get_column_header_name(
                                    current_schema, key)
                                column_name = self.escape_string(column_name)
                                if column_name not in custom_headers:
                                    custom_headers.append(column_name)

                except json.JSONDecodeError:
                    # Event type does not have schema, which is weird but not
                    # _technically_ invalid
                    current_schema = None
                    current_schema_order = {}

                event_export_data.append(current_event_type_data)
            # First, get the event details (schema data) in the correct order
            # for the headers above
            if event['event_details__data']:
                details = schema_utils.get_display_values_for_event_details(
                    event['event_details__data'].get('event_details', {}),
                    current_schema)
            else:
                details = {}

            schema_data = OrderedDict()
            for key, order in current_schema_order.items():
                item_display_name = schema_utils.get_display_value_header_for_key(
                    current_schema, key)
                schema_data[key] = self.escape_string(details.get(key, ''))
                column_name = schema_utils.get_column_header_name(
                    current_schema, key)
                schema_data[column_name] = self.escape_string(
                    details.get(item_display_name, ''))

            # Now assemble the data we want to write to the csv
            event_data = {
                "Report_Type": event_type.get('display', ''),
                "Report_Type_Internal_Value": event_type.get('value', ''),
                "Report_Id": event.get('serial_number', ''),
                "Title": self.escape_string(event.get('title', "")),
                "Priority": Event.PRIORITY_LABELS_MAP.get(
                    event.get('priority', ""), ''),
                "Priority_Internal_Value": event.get('priority', ''),
                "Report_Status": "Resolved" if event[
                    'state'] == Event.SC_RESOLVED else 'Active',
                reported_at.replace(" ", "_"): event['event_time'].astimezone(
                    current_tz).strftime('%Y-%m-%d %H:%M'),
                "Latitude": event['location'].y if event[
                    'location'] is not None else '',
                "Longitude": event['location'].x if event[
                    'location'] is not None else '',
                "Number_of_Notes": event.get('notes_count', ''),
                "Notes": self.escape_string(event.get('full_notes', '')),
                "Number_of_Related_Subjects": event.get('', ''),
                "Collection_Report_IDs": ';'.join(
                    (str(x) for x in event['parent_event_serial_numbers'] if
                     x is not None)),
                "CUSTOM_FIELDS_BEGIN_HERE": "",
            }

            # Use cached reported_by map
            reported_by_values = reported_by_map.get(
                str(event.get('reported_by_id', '')), '')
            event_data['Reported_By'] = reported_by_values.get(
                'display', '') if reported_by_values else ''

            for header in custom_headers:
                header_key = header.replace(' ', '_')
                # if header has been escaped
                if header.startswith('"') and header.endswith('"'):
                    header = header[1:-1]
                column_data = schema_data.get(header, "")
                event_data[header_key] = column_data if column_data else ""

            current_event_type_data['events'].append(event_data)

        if not combined_headers:
            combined_headers.extend(default_headers)
            combined_headers.extend(custom_headers)

        return {
            'event_export_data': event_export_data,
            'combined_headers': [header.replace(' ', '_') for header in
                                 combined_headers],
            'custom_headers': custom_headers
        }

    def escape_string(self, string):
        if not isinstance(string, str) or not string:
            return string
        strings = string.splitlines()
        string = " ".join(strings)
        return string

    def get(self, request, *args, **kwargs):
        self.value_cols = request.GET.get('value_cols', False)
        self.display_cols = request.GET.get('display_cols', True)

        csv_data = self.prepare_csv_data()

        response = HttpResponse(content_type='text/csv')
        response[
            'Content-Disposition'] = f'attachment; filename={csv_data["report_filename"]}'
        response['x-das-download-filename'] = csv_data['report_filename']

        writer = csv.DictWriter(response, fieldnames=csv_data['event_types'].get(
            'combined_headers'))
        writer.writeheader()
        event_types = csv_data['event_types']
        for event_type in event_types.get('event_export_data', []):
            for event in event_type.get('events', {}):
                writer.writerow(event)
        return response

    def prepare_csv_data(self, **kwargs):
        REPORT_TIME_FORMAT = '%-d %B %Y %Z' if platform.system().lower() != 'windows' else '%#d %B %Y %Z'
        current_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = current_tz.localize(datetime.utcnow())
        csv_data = {
            'report_filename': f'Event Export {timestamp.strftime("%Y-%m-%d")}.csv',
            'report_time': timestamp.strftime(REPORT_TIME_FORMAT),
            'event_types': self.get_event_export_list()
        }

        return csv_data

    def get_queryset(self):

        # TODO: Update to allow passing last_days constraint.

        queryset = Event.objects.all().prefetch_related('event_type')

        permitted_event_categories = get_permitted_event_categories(self.request)

        if len(permitted_event_categories) > 0:
            queryset = queryset.filter(event_type__category__in=permitted_event_categories)
        else:
            return queryset.none()

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

        contained_event_ids = queryset.filter(event_type__is_collection=True) \
            .aggregate(child_event_ids=ArrayAgg('out_relationship__to_event')) \
            .get('child_event_ids')

        if contained_event_ids:
            child_events = Event.objects.filter(id__in=contained_event_ids)
            queryset = queryset.distinct() | child_events.distinct()

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

    def add_segment_to_record(self, patrol_segment_id, new_record):
        for record in new_record:
            if not record.get('patrol_segments'):
                record['patrol_segments'] = patrol_segment_id if isinstance(patrol_segment_id, list) else [patrol_segment_id]
            else:
                record['patrol_segments'].append(patrol_segment_id)
        return new_record

    def post(self, request, *args, **kwargs):
        request.POST._mutable = True
        new_record = request.data
        if isinstance(new_record, dict):
            new_record = [new_record]

        patrol_segment = self.kwargs.get('patrol_segment')
        if patrol_segment:
            new_record = self.add_segment_to_record(patrol_segment, new_record)

        with transaction.atomic():
            errors = []
            serializer = self.get_serializer(data=new_record, many=True)
            if serializer.is_valid():
                serializer.save()
                data = serializer.data
                data = data if len(new_record) > 1 else data[0]
                return Response(data, status=status.HTTP_201_CREATED)
            else:
                errors.append(serializer.errors)
                for error in errors:
                    logger.exception(
                        'Invalid Event type(s) provided {}'.format(error))
                    return Response(errors, status=status.HTTP_400_BAD_REQUEST)

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

        context['include_related_events'] = parse_bool(
            query_params.get('include_related_events',
                             include_for_posts))
        context['include_notes'] = parse_bool(
            query_params.get('include_notes', include_for_posts))

        try:
            context['eventsource_id'] = request.data.get('eventsource_id')
        except AttributeError:
            pass

        return context

    def get_queryset(self):

        queryset = Event.objects.all_sort().prefetch_related(
            'eventsource_event_refs')
        patrol_segment_id = self.kwargs.get('patrol_segment')
        if patrol_segment_id:
            logger.debug("Filtering on patrol segment id: %s", patrol_segment_id)
            queryset = queryset.filter(patrol_segments__id=patrol_segment_id)

        query_params = self.request.query_params
        event_ids = query_params.get('event_ids', [])
        if event_ids:
            if isinstance(event_ids, str):
                event_ids = [event_ids, ]
            queryset = queryset.filter(id__in=event_ids)

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
                raise ValueError(
                    f"Invalid value for 'updated_since' = '{updated_since}'")

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
            return queryset.none()

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


def get_permitted_event_categories(request):
    permitted_categories = []

    for category in EventCategory.objects.filter(is_active=True):
        permission_name = 'activity.{0}_{1}'.format(
            category.value,
            EventCategoryPermissions.http_method_map['GET']
        )
        if request.user.has_perm(permission_name):
            permitted_categories.append(category)
    return permitted_categories


def calculate_event_etag(view_instance, view_method, request, *args, **kwargs):
    instance = view_instance.get_object()
    return str(hash(instance.updated_at))


class EventsGeoJsonView(EventsView):
    serializer_class = EventGeoJsonSerializer
    pagination_class = StandardResultsSetGeoJsonPagination
    renderer_classes = (ExtendedGEOJSONRenderer,)


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
                                           pk=self.kwargs.get('id'))
        return event


class EventNoteView(generics.RetrieveUpdateDestroyAPIView):
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
                request.data['filecontent.file'] = request.stream.FILES[
                    'filecontent.file']
            except KeyError:
                pass

        this_data = copy.copy(request.data)
        this_data['event'] = event.id

        this_data['usercontent.file'] = this_data['filecontent.file']

        serializer = self.get_serializer(data=this_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED,
                        headers=headers)

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
        self.check_object_permissions(self.request, obj)
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

        if isinstance(instance.usercontent.file,
                      (versatileimagefield.files.VersatileImageFieldFile,)):
            filename = get_stored_filename(instance.usercontent.file,
                                           rendition_set='default',
                                           rendition_key=desired_image_size)
            try:
                response_file = instance.usercontent.file.field.storage.open(
                    filename)
            except OSError as oe:
                logger.warning(
                    'Failed attempt to open file %s. Will default to original file version.',
                    filename)
                response_file = instance.usercontent.file

            response = HttpResponse(response_file, content_type=content_type)
        else:
            response = HttpResponse(
                instance.usercontent.file, content_type=content_type)
            response[
                'Content-Disposition'] = 'attachment; filename=%s' % instance.usercontent.filename

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
                                              pk=request.data.get(
                                                  'to_event_id'))

        relation = EventRelationship.objects.add_relationship(
            from_event=from_event, to_event=to_event,
            type=type, )

        serializer = self.get_serializer(relation)
        headers = self.get_success_headers(serializer.data)
        return response.Response(serializer.data,
                                 status=status.HTTP_201_CREATED,
                                 headers=headers)

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

    queryset = accounts.models.User.objects.none()


# Patrol Management API Views

class PatrolTypesView(generics.ListAPIView):
    serializer_class = PatrolTypeSerializer
    queryset = PatrolType.objects.all()


class PatrolTypeView(generics.RetrieveAPIView):
    lookup_field = 'id'
    serializer_class = PatrolTypeSerializer
    queryset = PatrolType.objects.all()


class PatrolSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = [
                {
                    'name': 'filter', 'in': 'query', 'required': False,
                    'description': 'example: {\"date_range\":{\"lower\":\"2020-09-16T00:00:00.000Z\"}}'}
            ]
            operation['parameters'].extend(query_params)
        return operation


class PatrolsView(generics.ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    serializer_class = PatrolSerializer
    schema = PatrolSchema()

    def get(self, request, *args, **kwargs):
        state_filters = self.request.query_params.getlist('state', None)
        if state_filters:
            allowed_state_filters = [e.value for e in StateFilters]
            if not (set(state_filters) <= set(allowed_state_filters)):
                return Response(
                    data={
                        'error': f'Only states: {", ".join(allowed_state_filters)} allowed for filtering'},
                    status=status.HTTP_400_BAD_REQUEST)
        return super().get(request, *args, **kwargs)

    def get_queryset(self):

        queryset = Patrol.objects.all()
        query_params = self.request.query_params
        patrol_filter = query_params.get('filter')
        if patrol_filter:
            try:
                patrol_filter = json.loads(patrol_filter)
                queryset = queryset.by_patrol_filter(patrol_filter)
            except json.JSONDecodeError:
                logger.exception(
                    'Invalid filter expression. filter=%s', patrol_filter)
                raise

        patrol_type = query_params.getlist('patrol_type', None)
        if patrol_type:
            queryset = queryset.by_patrol_type(patrol_type)

        state = query_params.getlist('state', None)
        if state:
            queryset = queryset.by_state(state)

        subject = query_params.getlist('subject', None)
        if subject:
            queryset = queryset.by_subject(subject)

        return queryset.sort_patrols()


class PatrolView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = 'id'
    serializer_class = PatrolSerializer
    queryset = Patrol.objects.all()


class PatrolNotesView(generics.ListCreateAPIView):
    # permission_classes = (PatrolNotesCategoryPermissions,)
    serializer_class = PatrolNoteSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        request.data['patrol'] = self.get_patrol()
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        return PatrolNote.objects.all().filter(patrol=self.get_patrol())

    def get_patrol(self):
        return generics.get_object_or_404(Patrol.objects.all(),
                                          pk=self.kwargs.get('id'))


class PatrolNoteView(generics.RetrieveUpdateAPIView):
    #permission_classes = (PatrolNotesCategoryPermissions,)
    serializer_class = PatrolNoteSerializer

    def get_queryset(self):
        notes = PatrolNote.objects.all().filter(patrol=self.get_patrol())
        return notes

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'id': self.kwargs['note_id']}

        obj = generics.get_object_or_404(queryset, **filters)

        return obj

    def get_patrol(self):
        return generics.get_object_or_404(Patrol.objects.all(),
                                          pk=self.kwargs['id'])


class PatrolFilesView(generics.ListCreateAPIView):
    # permission_classes = (PatrolCategoryPermissions,)
    serializer_class = PatrolFileSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):

        patrol = self.get_patrol()

        # TODO: This conditional is to handle the case where a file is uploaded
        # via XHR. Figure out why.
        if 'filecontent.file' not in request.data:
            try:
                # Ajax request.
                request.data['filecontent.file'] = request.stream.FILES[
                    'filecontent.file']
            except KeyError:
                return Response("filecontent.file not found", status=status.HTTP_400_BAD_REQUEST)

        this_data = copy.copy(request.data)
        this_data['patrol'] = patrol

        this_data['usercontent.file'] = this_data['filecontent.file']

        serializer = self.get_serializer(data=this_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED,
                        headers=headers)

    def get_queryset(self):
        return self.get_patrol().files.all()

    def get_patrol(self):
        return generics.get_object_or_404(Patrol.objects.all(),
                                          pk=self.kwargs.get('id'))


class PatrolFileView(generics.RetrieveUpdateDestroyAPIView):
    # permission_classes = (PatrolCategoryPermissions,)
    serializer_class = PatrolFileSerializer

    def get_queryset(self):
        return PatrolFile.objects.all().filter(patrol=generics.get_object_or_404(Patrol.objects.all(),
                                                                                 pk=self.kwargs['id']))

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'id': self.kwargs['filecontent_id']}

        obj = generics.get_object_or_404(queryset, **filters)
        return obj

    def get(self, request, *args, **kwargs):
        if self.kwargs.get('filename', None) == 'meta-data':
            return super().get(request, *args, **kwargs)

        instance = self.get_object()

        desired_image_size = self.kwargs.get('image_size', None)
        content_type, encoding = mimetypes.guess_type(
            instance.usercontent.filename)

        if content_type in USERCONTENT_FORCE_DOWNLOAD:
            content_type = 'application/octet-stream'

        if isinstance(instance.usercontent.file,
                      (versatileimagefield.files.VersatileImageFieldFile,)):
            filename = get_stored_filename(instance.usercontent.file,
                                           rendition_set='default',
                                           rendition_key=desired_image_size)
            try:
                response_file = instance.usercontent.file.field.storage.open(
                    filename)
            except OSError:
                logger.warning(
                    'Failed attempt to open file %s. Will default to original file version.',
                    filename)
                response_file = instance.usercontent.file

            response = HttpResponse(response_file, content_type=content_type)
        else:
            response = HttpResponse(
                instance.usercontent.file, content_type=content_type)
            response[
                'Content-Disposition'] = 'attachment; filename=%s' % instance.usercontent.filename

        return response


class PatrolsegmentsView(generics.ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    serializer_class = PatrolSegmentSerializer
    queryset = PatrolSegment.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        return get_segments(self.kwargs, queryset)


class PatrolsegmentView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = 'id'
    serializer_class = PatrolSegmentSerializer

    def get_queryset(self):
        queryset = PatrolSegment.objects.filter(id=self.kwargs.get('id'))
        return get_segments(self.kwargs, queryset)


def get_segments(kwargs, queryset):
    related_event = kwargs.get('event_id')
    if related_event:
        queryset = queryset.filter(eventrelatedsegments__event__id=related_event)
    return queryset
