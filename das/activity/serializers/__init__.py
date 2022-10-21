import copy
import json
import logging
import traceback
from collections import OrderedDict

import drf_extra_fields.geo_fields
import jsonschema
import pytz
from drf_extra_fields.geo_fields import PointField
from rest_framework_gis.serializers import GeoFeatureModelListSerializer
from versatileimagefield.serializers import VersatileImageFieldSerializer

import django.db
import rest_framework.serializers
import rest_framework.status
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point, Polygon
from django.core.exceptions import PermissionDenied
from django.core.validators import EmailValidator, RegexValidator
from django.http import Http404
from django.template.defaultfilters import truncatechars
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.fields import DateTimeField
from rest_framework.metadata import BaseMetadata
from rest_framework.request import clone_request
from rest_framework.utils.field_mapping import ClassLookupDict

import activity.models
import usercontent.serializers
import utils
import utils.schema_utils as schema_utils
from accounts.serializers import (UserDisplaySerializer, UserSerializer,
                                  get_user_display)
from activity.alerting.conditions import Conditions
from activity.event_geometries import GenericGeometryFactory
from activity.exceptions import SchemaValidationError
from activity.models import (PC_OPEN, Event, EventGeometry, EventsourceEvent,
                             EventType, PatrolSegment)
from activity.serializers.base import FileSerializerMixin
from activity.serializers.fields import EventGeometryField
from activity.util import get_permitted_event_categories
from choices.serializers import ChoiceField
from core.serializers import (ContentTypeField, GenericRelatedField,
                              PointValidator)
from core.utils import OneWeekSchedule
from observations.serializers import SubjectSerializer
from revision.manager import AC_RELATION_DELETED, AC_UPDATED
from utils.feature_representation import FeatureRepresentation
from utils.gis import get_polygon_info
from utils.json import parse_bool
from utils.schema_utils import (get_schema_renderer_method,
                                validate_rendered_schema_is_wellformed)

logger = logging.getLogger(__name__)

MAX_UPDATES_STR_LENGTH = 10


class DuplicateResourceError(APIException):
    default_status_code = rest_framework.status.HTTP_409_CONFLICT
    default_fieldname = 'unknown field'
    default_detail = 'The resource provided conflicts with an existing resource.'

    def __init__(self, fieldname=None, detail=None, status_code=None):

        self.status_code = status_code or self.default_status_code

        self.detail = {
            fieldname or self.default_fieldname: force_str(detail or self.default_detail)
        }


class EventAttributesField(rest_framework.serializers.JSONField):
    def __init__(self, event_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schema = None
        if event_type:
            self.schema = event_type.schema

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if not self.schema and data:
            rest_framework.serializers.ValidationError(
                'Schema not set for Event.Attributes')
        try:
            jsonschema.validate(data, self.schema)
        except jsonschema.exceptions.ValidationError as ex:
            raise rest_framework.serializers.ValidationError(ex.message)
        return data


class CommunitySerializer(rest_framework.serializers.ModelSerializer):
    content_type = ContentTypeField()

    class Meta:
        model = activity.models.Community
        fields = ('name', 'id', 'content_type')

    def to_internal_value(self, data):
        if not 'id' in data:
            raise ValidationError('Missing id in deserializing User object')
        obj = activity.models.Community.objects.get(id=data['id'])
        return obj


def filter_blank_choice(choices):
    if isinstance(choices, dict):
        choices = choices.items()
    for value, display in choices:
        try:
            if display.startswith('-----'):
                continue
        except AttributeError:
            pass
        yield value, display


class EventJSONSchema(BaseMetadata):
    label_lookup = ClassLookupDict({
        rest_framework.serializers.Field: 'object',
        rest_framework.serializers.BooleanField: 'boolean',
        rest_framework.serializers.NullBooleanField: 'boolean',
        rest_framework.serializers.CharField: 'string',
        rest_framework.serializers.URLField: 'string',
        rest_framework.serializers.EmailField: 'string',
        rest_framework.serializers.RegexField: 'string',
        rest_framework.serializers.SlugField: 'string',
        rest_framework.serializers.IntegerField: 'integer',
        rest_framework.serializers.FloatField: 'number',
        rest_framework.serializers.DecimalField: 'number',
        rest_framework.serializers.DateField: 'string',
        rest_framework.serializers.DateTimeField: 'string',
        rest_framework.serializers.TimeField: 'string',
        rest_framework.serializers.FileField: 'string',
        rest_framework.serializers.ChoiceField: 'enum',
        rest_framework.serializers.MultipleChoiceField: 'string',
        rest_framework.serializers.ListField: 'array',
        rest_framework.serializers.DictField: 'object',
        rest_framework.serializers.Serializer: 'object',
        rest_framework.serializers.PrimaryKeyRelatedField: 'string',
        rest_framework.serializers.SlugRelatedField: 'enum',
        rest_framework.serializers.UUIDField: 'string',
        rest_framework.serializers.RelatedField: 'object',
        rest_framework.serializers.HyperlinkedRelatedField: 'string',
        rest_framework.serializers.HyperlinkedIdentityField: 'string',
        drf_extra_fields.geo_fields.PointField: 'string',
        ChoiceField: 'string',

    })

    ignore_choices_lookup = ClassLookupDict({
        rest_framework.serializers.ManyRelatedField: True
    })

    schema = {
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'type': 'object',
        'properties': {},
        'required': [],
        'dependencies': {}
    }

    def determine_metadata(self, request, view):
        metadata = OrderedDict(self.schema)

        if hasattr(view, 'get_serializer'):
            properties = self.determine_properties(request, view)
            metadata['properties'] = properties
        metadata['description'] = view.get_view_description()
        return metadata

    def determine_properties(self, request, view):
        """Return the schema properties for a view"""

        actions = {}
        for method in {'PUT', 'POST'} & set(view.allowed_methods):
            view.request = clone_request(request, method)
            try:
                # Test global permissions
                if hasattr(view, 'check_permissions'):
                    view.check_permissions(view.request)
                # Test object permissions
                if method == 'PUT' and hasattr(view, 'get_object'):
                    view.get_object()
            except (APIException, PermissionDenied, Http404):
                pass
            else:
                # If user has appropriate permissions for the view, include
                # appropriate metadata about the fields that should be
                # supplied.
                serializer = view.get_serializer()
                return self.get_serializer_info(serializer)
            finally:
                view.request = request

        return actions

    def get_serializer_info(self, serializer):
        """
        Given an instance of a serializer, return a dictionary of metadata
        about its fields.
        """
        if hasattr(serializer, 'child'):
            # If this is a `ListSerializer` then we want to examine the
            # underlying child serializer instance instead.
            serializer = serializer.child

        def get_fields():
            for field_name, field in serializer.fields.items():
                value = self.get_field_info(field)
                if value:
                    yield (field_name, value)

        return OrderedDict([(key, value) for key, value in get_fields()
                            ])

    def get_field_info(self, field):
        """
        Given an instance of a serializer field, return a dictionary
        of metadata about it.
        """
        field_info = OrderedDict()
        try:
            field_info['type'] = self.label_lookup[field]
        except KeyError:
            logger.debug(
                'Unsupported field {0} type {1} for JSON schema'.format(
                    field.field_name, type(field)))
            return None

        ignore_choices = False
        try:
            ignore_choices = self.ignore_choices_lookup[field]
        except KeyError:
            pass

        field_info['required'] = getattr(field, 'required', False)

        attr_map = {
            'label': 'title', 'help_text': 'description',
            'min_length': 'minLength', 'max_length': 'maxLength',
            'min_value': 'minimum', 'max_value': 'maximum'
        }

        for key, dest_key in attr_map.items():
            value = getattr(field, key, None)
            if value is not None and value != '':
                field_info[dest_key] = value

        if not field_info.get('read_only') and not ignore_choices:
            try:
                object_choices = field.object_choices
            except AttributeError:
                try:
                    choices = field.choices
                except AttributeError:
                    pass
                else:
                    field_info['enum_ext'] = [
                        {
                            'value': choice_value,
                            'title': force_str(choice_name, strings_only=True)
                        }
                        for choice_value, choice_name in filter_blank_choice(choices)
                    ]
                    field_info['enum'] = [v['value'] for v in
                                          field_info['enum_ext']]
            else:
                if isinstance(object_choices, dict):
                    unassigned = []
                    enum_ext = {}
                    for group, values in filter_blank_choice(object_choices):
                        if isinstance(values, (list, tuple, dict)):
                            if isinstance(values, dict):
                                values_iter = values.items()
                            else:
                                values_iter = iter(values)
                            enum_ext[group] = [
                                {
                                    'value': choice_value,
                                    'title': force_str(choice_name,
                                                       strings_only=True)
                                }
                                for choice_value, choice_name in filter_blank_choice(values_iter)
                            ]
                        else:
                            unassigned.append({
                                'value': group,
                                'title': force_str(values, strings_only=True)
                            })
                    if not enum_ext:
                        enum_ext = unassigned
                else:
                    enum_ext = [
                        {
                            'value': choice_value,
                            'title': force_str(choice_name, strings_only=True)
                        }
                        for choice_value, choice_name in filter_blank_choice(object_choices)
                    ]
                    field_info['enum'] = [v['value'] for v in
                                          enum_ext]
                field_info['enum_ext'] = enum_ext

        return field_info


class ReportedByRelatedField(GenericRelatedField):
    def get_field_mapping(self, label="ReportedBy"):
        return super().get_field_mapping(label)

    def check_has_event_category_permission(self):
        # Checks if the user has any event-category permission.
        event_categories = activity.models.EventCategory.objects.values_list(
            'value').distinct()
        event_categories = [ec[0] for ec in event_categories]
        actions = ('create', 'update', 'read', 'delete')
        request = self.context.get('request')

        for event_category in event_categories:
            permission_name = [
                f'activity.{event_category}_{action}' for action in actions]
            for perm in permission_name:
                if request.user.has_perm(perm):
                    return True

    def get_object_queryset(self):
        if not self.check_has_event_category_permission():
            return False

        request = self.context.get('request')

        for p in activity.models.Event.PROVENANCE_CHOICES:
            provenance = p[0]
            values = list(
                activity.models.Event.objects.get_reported_by_for_provenance(
                    provenance, request.user))
            if values:
                yield (provenance, values)


class EventTypeRelatedField(rest_framework.serializers.RelatedField):
    def get_queryset(self):
        queryset = activity.models.EventType.objects.all_sort()
        if self.context.get('view').get_view_name() == 'Event Schema':
            event_categories = activity.models.EventCategory.objects.values_list(
                'value').distinct()
            event_categories = [ec[0] for ec in event_categories]
            actions = ('create', 'update', 'read', 'delete')
            allowed_event_categories = []
            for event_category in event_categories:
                permission_name = [
                    f'activity.{event_category}_{action}' for action in actions]
                if any([self.context.get('request').user.has_perm(perm) for perm in permission_name]):
                    allowed_event_categories.append(event_category)

                return queryset.by_category(allowed_event_categories) if allowed_event_categories else queryset.none()
        else:
            return queryset

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):

        if data:
            try:
                return activity.models.EventType.objects.get_by_value(data)
            except activity.models.EventType.DoesNotExist:
                raise rest_framework.serializers.ValidationError(
                    {'event_type': 'Value \'%s\' does not exist.' % data})
        else:
            request_data = self.context['request'].data
            external_event_type = request_data.get('external_event_type')
            if external_event_type:
                eventsource = resolve_external_event_source()
                if eventsource:
                    return eventsource.event_type

        return None

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display)
                            for row in self.get_queryset()))


class EventSourceRelatedField(rest_framework.serializers.RelatedField):

    def get_queryset(self):
        user = self.context['request'].user
        return activity.models.EventSource.objects.filter(eventprovider__owner=user)

    def to_representation(self, value):
        return value.id if value else None

    def to_internal_value(self, data):

        if data:
            try:
                user = self.context['request'].user
            except AttributeError:
                pass
            else:
                try:
                    return activity.models.EventSource.objects.get(id=data, eventprovider__owner=user)
                except activity.models.EventSource.DoesNotExist:
                    raise rest_framework.serializers.ValidationError(
                        {'eventsource': 'ID \'%s\' does not exist.' % data})
        return None

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display)
                            for row in self.get_queryset()))


def get_allowed_actions_for_category(user, category_name):
    allowed_actions = set()
    geo_perm_actions = ("view", "add", "change", "delete")

    actions = {
        "create": "create",
        "update": "update",
        "read": "read",
        "delete": "delete",
        "add": "create",
        "change": "update",
        "view": "read",
    }

    for action in ('create', 'update', 'read', 'delete') + geo_perm_actions:
        perm_name = f"activity.{category_name}_{action}"
        geo_perm_name = f"activity.{action}_{category_name}_geographic_distance"
        if user.has_perm(perm_name) or user.has_perm(geo_perm_name):
            action = actions[action]
            allowed_actions.add(action)
    return list(allowed_actions)


class EventCategorySerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = activity.models.EventCategory
        read_only_fields = ('id',)
        fields = ('id', 'value', 'display', 'is_active', 'ordernum', 'flag',)

    def to_representation(self, obj):
        rep = super().to_representation(obj)

        # If we know the user requesting the category, include their permissions
        # for that category
        request = self.context.get('request', None)
        user, method = getattr(request, 'user', None), getattr(
            request, 'method', None)
        if user is not None and method == 'GET':
            rep['permissions'] = get_allowed_actions_for_category(
                user, rep['value'])
        return rep


class EventCategoryRelatedField(rest_framework.serializers.RelatedField):

    def to_representation(self, value):
        rep = EventCategorySerializer().to_representation(value)
        user = getattr(self.context.get('request', None), 'user', None)
        if user is not None:
            rep['permissions'] = get_allowed_actions_for_category(
                user, rep['value'])
        return rep

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                event_category = activity.models.EventCategory.objects.get_by_value(
                    data)
            except activity.models.EventCategory.DoesNotExist:
                raise ValidationError(
                    f'event_category: {data} does not exist.')
            else:
                return event_category

    def get_queryset(self):
        return activity.models.EventCategory.objects.all_sort()

    def get_choices(self, cutoff=None):
        queryset = self.get_queryset()
        if queryset is None:
            return {}

        if cutoff is not None:
            queryset = queryset[:cutoff]

        return OrderedDict([(self.to_representation(item).get('value'),
                             self.display_value(item)) for item in queryset])


class EventTypeSerializer(rest_framework.serializers.ModelSerializer):
    category = EventCategoryRelatedField()

    class Meta:
        model = activity.models.EventType
        read_only_fields = ('id',)
        write_only_fields = ('icon',)
        fields = read_only_fields + write_only_fields + ('value', 'display', 'ordernum',
                                                         'is_collection', 'category', 'icon_id', 'is_active', 'schema',
                                                         'default_priority', 'geometry_type')

    def __init__(self, *args, **kwargs):
        super(EventTypeSerializer, self).__init__(*args, **kwargs)
        self.request = self.context.get('request')

        if not self.context.get('include_schema', False) and self.request.method == 'GET':
            self.fields.pop('schema')

    @staticmethod
    def validate_schema(schema):
        try:
            rendered_schema = get_schema_renderer_method()(schema)
        except NameError as exc:
            raise ValidationError(exc)
        except ValueError as exc:
            raise ValidationError(exc)
        except Exception as exc:
            raise ValidationError(exc)
        else:
            try:
                validate_rendered_schema_is_wellformed(rendered_schema)
            except SchemaValidationError as exc:
                raise ValidationError(exc)
        return schema

    def to_internal_value(self, data):
        if data.get('icon_id'):
            data['icon'] = data['icon_id']

        return super().to_internal_value(data)

    @staticmethod
    def is_schema_readonly(schema):
        try:
            rendered = get_schema_renderer_method()(schema)
        except Exception:
            pass
        else:
            _schema = rendered.get('schema', {})
            return True if parse_bool(_schema.get('readonly')) else False

    def to_representation(self, obj):
        rep = super().to_representation(obj, )
        rep['url'] = utils.add_base_url(
            self.request, reverse('eventtype', args=[obj.id, ]))

        if self.is_schema_readonly(obj.schema):
            rep['readonly'] = True
        return rep


class EventRelationshipTypeRelatedField(rest_framework.serializers.RelatedField):
    def get_queryset(self):
        return activity.models.EventRelationshipType.objects.all_sort()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            return activity.models.EventRelationshipType.objects.get_by_value(data)
        return None

    @property
    def choices(self):
        return OrderedDict(((row.value, row.value)
                            for row in self.get_queryset()))


def get_update_type(revision, previous_revisions=[]):
    field_mapping = (('location', 'update_location'), ('message', 'update_message'),
                     ('event_time', 'update_datetime'), ('reported_by_id',
                                                         'update_reported_by'),
                     ('state', 'update_event_state'), ('priority',
                                                       'update_event_priority'),
                     ('event_type', 'update_event_type'))
    model_name = revision._meta.model_name
    action = revision.action
    data = revision.data
    if action == 'added':
        return 'add_{0}'.format(model_name.replace('revision', ''))
    elif action == 'updated':
        event_state = data.get('state', None)
        if event_state:
            if event_state == activity.models.Event.SC_RESOLVED:
                return activity.models.Event.SC_RESOLVED
            if event_state == activity.models.Event.SC_NEW:
                return 'mark_as_new'
            for row in reversed(previous_revisions):
                prev_state = row.data.get('state', None)
                if prev_state:
                    if prev_state == activity.models.Event.SC_RESOLVED:
                        return 'unresolved'
                    if (prev_state == activity.models.Event.SC_NEW
                            and event_state == activity.models.Event.SC_ACTIVE):
                        return 'read'
                    break
        for k, v in field_mapping:
            if k in data:
                return v
        return 'update_event'
    return 'other'


class EventNoteSerializer(rest_framework.serializers.ModelSerializer):
    id = rest_framework.serializers.UUIDField(required=False, read_only=False)
    created_by_user = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )

    class Meta:
        model = activity.models.EventNote
        read_only_fields = ('created_at', 'updated_at')
        write_only_fields = ('event',)
        fields = ('id', 'created_by_user',
                  'text') + write_only_fields + read_only_fields

    def to_representation(self, note):
        rep = super().to_representation(note)
        rep['updates'] = self.render_updates(note)
        return rep

    def get_display_value(self, note):
        return '{0}: {1}'.format(get_user_display(note.created_by_user), note.text)

    def render_updates(self, note):
        def get_action(revision):
            if revision.action == AC_UPDATED:
                field_mapping = {'text': 'Note Text'}
                fieldnames = [field_mapping[k] for k in revision.data.keys() if
                              k in field_mapping]
                return '{0} fields: {1}'.format(revision.get_action_display(),
                                                ', '.join(fieldnames))

            return revision.get_action_display()

        return [
            dict(message='Note {action}'.format(
                action=get_action(revision),
                user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get('text', ''),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=get_update_type(revision),
            )
            for revision in note.revision.all_user()
        ]


class EventStateSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = activity.models.Event
        fields = ('state',)

    def update(self, instance, validated_data):
        update_fields = []
        for k, v in validated_data.items():
            if getattr(instance, k) != v:
                setattr(instance, k, v)
                update_fields.append(k)
        if update_fields:
            instance.save(update_fields=update_fields)
        return instance


class EventPhotoSerializer(rest_framework.serializers.ModelSerializer):
    created_by_user = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )

    image = VersatileImageFieldSerializer(sizes='event_photo')

    class Meta:
        model = activity.models.EventPhoto
        read_only_fields = ('created_at', 'updated_at', 'created_by_user',)
        fields = ('id', 'image', 'filename', 'event') + read_only_fields

    def to_representation(self, photo):
        rep = super().to_representation(photo)
        rep['updates'] = self.render_updates(photo)
        if 'request' in self.context:
            rep['url'] = utils.add_base_url(self.context['request'],
                                            reverse('event-view-photo',
                                                    args=[photo.event.id, photo.id]))
        else:
            logger.warning('missing request in EventPhotoSerializer context: %s',
                           traceback.format_stack())

        return rep

    def render_updates(self, photo):
        def get_action(revision):
            return revision.get_action_display()

        return [
            dict(message='Photo {action}'.format(
                action=get_action(revision),
                user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get('text', ''),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=get_update_type(revision),
            )
            for revision in photo.revision.all_user()
        ]


class EventFileSerializer(FileSerializerMixin, rest_framework.serializers.ModelSerializer):
    usercontent_id = rest_framework.serializers.UUIDField(required=False)
    usercontent_type = rest_framework.serializers.PrimaryKeyRelatedField(
        required=False, queryset=ContentType.objects.all())

    usercontent = usercontent.serializers.UserContentSerializer(required=False)

    created_by = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )

    comment = rest_framework.serializers.CharField(
        allow_blank=True, required=False,)

    class Meta:
        model = activity.models.EventFile
        read_only_fields = ('created_at', 'updated_at', 'created_by')
        fields = ('id', 'event', 'comment', 'usercontent',
                  'usercontent_id', 'usercontent_type') + read_only_fields

    @property
    def parent_name(self):
        return "event"

    def get_instance_parent_id(self, instance):
        return instance.event.id

    def get_update_type(self, revision, previous_revisions=[]):
        return get_update_type(revision, previous_revisions)


class EventDetailsSerializer(rest_framework.serializers.ModelSerializer):

    class Meta:
        model = activity.models.EventDetails
        read_only_fields = ('created_at', 'updated_at')
        fields = ('id', 'event', 'data') + read_only_fields

    def create(self, validated_data):
        return activity.models.EventDetails.objects.create_event_details(**validated_data)

    def update(self, instance, validated_data):

        # it's possibile that we weren't able to validate event data earlier,
        # so do it now
        if '_internal_validated' in validated_data['event_details'] and not validated_data['event_details']['_internal_validated']:
            del(validated_data['event_details']['_internal_validated'])
            validated_data = {'event_details': self._to_internal_value_inner(
                instance, validated_data['event_details'])}

        # Get the current details object
        current_details = self.get_attribute(instance)

        if not current_details:
            current_details = activity.models.EventDetails.objects.create(
                event=instance, data=validated_data, update_parent_event=False)
            logger.info(
                f'Event Details created successfully for event id: {instance.id}')

        elif current_details.data != validated_data:
            current_details.data = validated_data
            current_details.save()
            logger.info(f'Event Details updated for event id: {instance.id}')

        return current_details

    def get_event_type(self, event):
        event_type = event.event_type
        if 'request' in self.context and 'event_type' in getattr(self.context['request'], 'data', {}):
            new_event_type = self.context['request'].data['event_type']
            if new_event_type and new_event_type != event_type.value:
                event_type = activity.models.EventType.objects.get(
                    value=new_event_type)
        return event_type

    def get_schema_fields_possible_values(self, schema):
        replacement_fields = schema_utils.get_replacement_fields_in_schema(
            schema)

        parameters = {}
        for replacement_field in replacement_fields:
            # No need to get values, only need value to name mapping
            if replacement_field['type'] not in ['names', 'map']:
                continue

            if replacement_field['lookup'] == 'enum':
                parameters[replacement_field['field']] = schema_utils.get_enum_choices(
                    replacement_field, as_string=False)
            elif replacement_field['lookup'] == 'query':
                parameters[replacement_field['field']] = schema_utils.get_dynamic_choices(
                    replacement_field, as_string=False)
            elif replacement_field['lookup'] == 'table':
                parameters[replacement_field['field']] = schema_utils.get_table_choices(
                    replacement_field, as_string=False)

        all_schema_fields = schema_utils.get_all_fields(schema)
        return all_schema_fields, parameters

    def _to_internal_value_inner(self, instance, data):
        if instance is None:
            data['_internal_validated'] = False
            return data

        event_type = self.get_event_type(instance)

        schema = event_type.schema

        if not schema:
            return super().to_internal_value(data)

        # Auto-generate a schema if appropriate.
        if schema_utils.should_auto_generate(schema):
            schema = schema_utils.generate_event_type_schema_from_doc(data)
            # Downstream code is expecting a template (as a string).
            schema = json.dumps(schema, indent=2)
            activity.models.EventType.objects.filter(
                id=event_type.id).update(schema=schema)

        all_schema_fields, parameters = self.get_schema_fields_possible_values(
            schema)

        # Append field information to the data we're getting so we know how to
        # get back to the source
        ret = {}
        for k, v in data.items():
            if k not in all_schema_fields:
                continue
            if type(v) == dict and k in parameters and v['value'] in parameters[k]:
                ret[k] = {'name': parameters[k]
                          [v['value']], 'value': v['value']}
            elif type(v) == list and k in parameters:
                all_values = []
                for value in v:
                    matches = []
                    for d in parameters[k]:
                        if isinstance(d, dict) and d['value'] == value:
                            matches.append(d)
                        elif value == d:
                            matches.append(value)

                    if len(matches) > 0:
                        all_values.append(matches[0])
                if len(all_values) > 0:
                    ret[k] = all_values
            else:
                ret[k] = v
        return ret

    def to_internal_value(self, data):
        return self._to_internal_value_inner(self.root.instance, data)

    def sanitize_event_details_for_api(self, event_details):
        """
        The select properties are still stored as a dictionary but returned to
        the API caller as a single value.
        Properties are stored as dictionaries for the report csv export to work
        properly

        :param event_details:
        :return:
        """
        for k, v in event_details.items():
            if k == "updates":
                continue
            elif isinstance(v, dict) and 'value' in v.keys():
                event_details[k] = v['value']
            elif isinstance(v, list):
                values = [x['value'] if isinstance(
                    x, dict) and 'value' in x.keys() else x for x in v]
                event_details[k] = values
        return event_details

    def to_representation(self, event_details):
        if not event_details:
            return OrderedDict()
        rep = OrderedDict(event_details.data['event_details'])
        event_type = self.get_event_type(event_details.event)
        rep['updates'] = self.render_updates(event_details, event_type)
        rep = self.sanitize_event_details_for_api(rep)
        return rep

    def render_updates(self, event_details, event_type):
        schema = event_type.schema
        rendered_schema = schema_utils.get_schema_renderer_method()(schema)
        last_details = None

        def get_action(revision):
            nonlocal last_details
            result = None
            fieldnames = []
            revision_details = revision.data.get(
                'data', {}).get('event_details', {})
            details = schema_utils.get_display_values_for_event_details(
                revision_details, rendered_schema)

            if revision.action == AC_UPDATED:
                for k, v in revision_details.items():
                    if k not in details:
                        continue
                    if last_details and last_details.get(k) == v:
                        continue

                    title = schema_utils.get_display_value_header_for_key(
                        rendered_schema, k)
                    display = details.get(title, '')
                    display = truncatechars(display, MAX_UPDATES_STR_LENGTH)
                    fieldnames.append(f"{title}")

                result = '{0} fields: {1}'.format(revision.get_action_display(),
                                                  ', '.join(fieldnames))

            last_details = revision_details
            return result

        updates = []
        for revision in event_details.revision.all_user():
            update_action = get_action(revision)
            if update_action:
                updates.append(
                    dict(message='{action}'.format(
                        action=update_action,
                        user=get_user_display(revision.user)),
                        time=revision.revision_at.isoformat(),
                        text=revision.data.get('text', ''),
                        user=UserDisplaySerializer().to_representation(revision.user),
                        type=get_update_type(revision),
                    )
                )
        return updates

    def is_valid(self, raise_exception=False):
        return super().is_valid(raise_exception=raise_exception)

    def get_attribute(self, instance):
        return activity.models.EventDetails.objects.filter(event=instance).order_by('created_at').last()


class EventSerializerMixin:

    def to_internal_value(self, data):
        internal_value = super().to_internal_value(data)

        for x in ('contains', 'is_linked_to', 'collection'):
            if x in data:
                internal_value[x] = data[x]

        return internal_value

    def create(self, validated_data):
        return self.create_event(validated_data)

    def create_event(self, validated_data):

        details_data = {}

        if 'event_details' in validated_data:
            details_data['event_details'] = validated_data['event_details']
            del validated_data['event_details']

        event_notes = validated_data.pop('notes', [])

        # [_.type for _ in activity.models.EventRelationshipType.objects.all()]
        rel_types = ('contains', 'is_linked_to',)

        relationship_data = {}
        for key in rel_types + ('collection',):
            if key in validated_data:
                relationship_data[key] = validated_data.pop(key)

        related_subjects = validated_data.pop('related_subjects', ())

        eventsource = validated_data.pop('eventsource', None)
        external_event_id = validated_data.pop('external_event_id', None)

        new_event = activity.models.Event.objects.create_event(
            **validated_data)

        EventDetailsSerializer().update(new_event, details_data)

        if eventsource and external_event_id:
            try:
                activity.models.EventsourceEvent.objects.add_relation(new_event,
                                                                      eventsource, external_event_id)

            except django.db.utils.IntegrityError:
                raise DuplicateResourceError(
                    fieldname='external_event_id', detail='External event ID already exists.'
                )

        for note in event_notes:
            note = copy.deepcopy(note)
            note['event'] = new_event.id
            enser = EventNoteSerializer(data=note,
                                        context=self.context)
            enser = enser.is_valid(raise_exception=True)
            enser.create(enser.validated_data)

        for related_subject in related_subjects:
            activity.models.EventRelatedSubject.objects.get_or_create(
                subject=related_subject, event=new_event)

        for relationship_type in rel_types:
            if relationship_type in relationship_data:

                related = relationship_data.pop(relationship_type)
                if not isinstance(related, (list, set)):
                    related = [related, ]

                children = [self.create_event(
                    self.to_internal_value(child)) for child in related]

                for child in children:
                    activity.models.EventRelationship.objects.add_relationship(from_event=new_event, to_event=child,
                                                                               type=relationship_type)

        if 'collection' in relationship_data:
            parent = relationship_data.pop('collection')
            parent = activity.models.Event.objects.get(id=parent['id'])
            if parent:
                activity.models.EventRelationship.objects.add_relationship(from_event=parent, to_event=new_event,
                                                                           type='contains')

        return activity.models.Event.objects.get(id=new_event.id)

    def update(self, instance, validated_data):

        logger.info('Inside update: %s', validated_data)
        update_fields = []

        patrol_segments = validated_data.pop('patrol_segments', None)
        if patrol_segments:
            logger.info('setting patrol segments. with %s', patrol_segments)
            # update_fields.append('patrol_segments')
            instance.patrol_segments.set(patrol_segments)

        for k, v in validated_data.items():
            # details don't get saved in the same table as the rest of the
            # event data, so hand this off and pretend we never saw it
            if k == 'event_details':
                EventDetailsSerializer().update(instance, {k: v})
                continue
            if k == 'notes':
                for note in v:
                    note = copy.deepcopy(note)
                    note['event'] = instance.id
                    note_id = note.pop('id', None)
                    enser = EventNoteSerializer(data=note,
                                                context=self.context)
                    enser.is_valid(raise_exception=True)
                    if note_id:
                        note_instance = activity.models.EventNote.objects.get(
                            id=note_id)
                        enser.update(note_instance, enser.validated_data)
                    else:
                        enser.create(enser.validated_data)
                continue

            if getattr(instance, k) != v:
                setattr(instance, k, v)
                if k == 'reported_by':
                    update_fields.append('reported_by_id')
                    update_fields.append('reported_by_content_type_id')
                elif k not in ('id',):
                    update_fields.append(k)

        if update_fields:
            instance.save(update_fields=update_fields)
        return instance

    def render_updates(self, event):
        def get_action(revision):
            if revision.action == AC_UPDATED:
                field_mapping = {'message': 'Description',
                                 'event_time': 'Time',
                                 'state': 'State is {0}',
                                 'priority': 'Priority is {0}',
                                 'location': 'Location',
                                 'reported_by_id': 'Reported By',
                                 'provenance': 'Reporter',
                                 'event_type': 'Report Type is {0}',
                                 'created_by_user': 'Report Author',
                                 'title': 'Title'}
                fieldnames = [field_mapping[k].format(event.get_display_value(k, v)) for k, v in revision.data.items() if
                              k in field_mapping]
                return '{0} fields: {1}'.format(revision.get_action_display(),
                                                ', '.join(fieldnames))
            elif revision.action == AC_RELATION_DELETED:
                field_mapping = {'message': 'Description',
                                 'related_query_name': '{}'
                                 }
                fieldnames = [field_mapping[k].format(revision.data[k]) for k, v in revision.data.items() if
                              k in field_mapping]
                return '{0} fields: {1}'.format(revision.get_action_display(),
                                                ', '.join(fieldnames))

            return revision.get_action_display()

        result = []

        if hasattr(event, "revisions"):
            revisions = list(iter(event.revisions))
        else:
            revisions = list(
                iter(event.revision.all_user().order_by('sequence')))

        while revisions:
            revision = revisions.pop()
            record = dict(
                message='{action}'.format(
                    action=get_action(revision),
                    user=self.get_user_display(revision.user, event)
                ),
                time=revision.revision_at.isoformat(),
                user=self.get_revision_user(revision.user, event),
                type=get_update_type(revision, revisions))
            result.append(record)
        return result

    def get_user_display(self, user, event):
        if user:
            return get_user_display(user)
        return event.get_provenance_display()

    def get_revision_user(self, user, event):
        if user:
            return UserDisplaySerializer().to_representation(
                user)
        return {'first_name': event.get_provenance_display(),
                'last_name': '',
                'username': event.provenance}


class EventHeaderSerializer(EventSerializerMixin, rest_framework.serializers.ModelSerializer):
    '''
    This is intended to serialize only 'header' fields for an Event, and especially to avoid
    serializing nested events.
    '''

    event_type = EventTypeRelatedField(required=False)
    updated_at = DateTimeField(
        source='sort_at', required=False, read_only=True)

    class Meta:
        model = activity.models.Event
        fields = ('id', 'message', 'time', 'end_time',
                  'serial_number', 'priority', 'event_type', 'icon_id',
                  'created_at', 'updated_at', 'title', 'state')

    def to_representation(self, event):
        rep = super().to_representation(event)
        if 'request' in self.context:
            request = self.context['request']
            rep['url'] = utils.add_base_url(request,
                                            reverse('event-view',
                                                    args=[event.id, ]))

            image_url = resolve_image_url(event)
            rep['image_url'] = utils.add_base_url(request, image_url)

            if event.location is not None:
                geodata = make_feature(self.context['request'], event)
                rep['geojson'] = geodata

        if event.event_type and event.event_type.category:
            rep['event_category'] = event.event_type.category.value

        rep['is_collection'] = event.event_type.is_collection

        return rep


class EventRelationshipSerializer(rest_framework.serializers.ModelSerializer):

    def to_internal_value(self, data):
        return super().to_internal_value(data)
    type = EventRelationshipTypeRelatedField()

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        if 'request' in self.context:
            request = self.context['request']

            # 'url' represents the proper relationship (from_event : to_event) regardless of the direction of this
            # serialization.
            rep['url'] = utils.add_base_url(request, reverse('event-view-relationship', args=[instance.from_event_id,
                                                                                              instance.type.value,
                                                                                              instance.to_event_id, ]))
        direction = self.context.get('event_relationship_direction', 'out')
        if direction == 'out':
            related_event = instance.to_event
        else:
            related_event = instance.from_event

        # related_event = instance.to_event if direction == 'out' else instance.from_event

        rep['related_event'] = EventHeaderSerializer(
            instance=related_event, many=False, context=self.context).data

        return rep

    def validate(self, attrs):
        to_event_id = attrs.get('to_event_id')
        if to_event_id and to_event_id == self.instance.from_event.id:
            raise rest_framework.serializers.ValidationError(
                'An event may not be related to itself.')
        return super().validate(attrs)

    class Meta:
        model = activity.models.EventRelationship
        read_only_fields = ('created_at', 'updated_at',)
        fields = ('type', 'ordernum',)


def resolve_image_url(event):
    return event.image_url


def resolve_external_event_source(user, external_event_type):
    ''' Resolve external event source.'''
    try:
        eventsource = activity.models.EventSource.objects.get(
            owner=user, external_event_type=external_event_type
        )
        return eventsource
    except activity.models.EventSource.DoesNotExist:
        pass


class OptimizedEventRelationshipSerializer(EventRelationshipSerializer):
    type = EventRelationshipTypeRelatedField()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if 'request' in self.context:
            request = self.context['request']
            rep['url'] = utils.add_base_url(request,
                                            reverse('event-view-relationship', args=[instance.from_event_id,
                                                                                     instance.type.value,
                                                                                     instance.to_event_id, ]))

            direction = self.context.get('event_relationship_direction', 'out')
            if direction == 'out':
                related_event = instance.to_event
            else:
                related_event = instance.from_event

            rep['related_event'] = PatrolSegmentEventSerializer(instance=related_event, many=False,
                                                                context={'include_related_events': False, 'request': request}).data
            return rep


class PatrolSegmentEventSerializer(EventSerializerMixin, rest_framework.serializers.ModelSerializer):
    updated_at = DateTimeField(read_only=True)
    title = rest_framework.serializers.CharField(
        required=False, allow_blank=True)
    event_type = EventTypeRelatedField(required=False)
    contains = rest_framework.serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.context.get('include_related_events', False):
            self.fields.pop('contains')

    class Meta:
        model = activity.models.Event
        fields = ('id',
                  'serial_number',
                  'event_type', 'priority', 'title',
                  'state',  'contains', 'updated_at')

    def get_contains(self, event):
        return self.get_out_relation(event, 'contains')

    def get_out_relation(self, event, value):
        self.context['event_relationship_direction'] = 'out'
        qs = event.out_relationships.filter(
            type__value=value).all().order_by('ordernum', 'to_event__created_at')
        serializer = OptimizedEventRelationshipSerializer(
            instance=qs, many=True, context=self.context,)
        return serializer.data

    def to_representation(self, event):
        rep = super().to_representation(event)
        if event.location is not None:
            geodata = make_feature(self.context['request'], event)
            rep['geojson'] = geodata

        if event.event_type:
            rep['is_collection'] = event.event_type.is_collection

        return rep


def which_field_search_for(application):
    if application and application.client_id == "cybertracker":
        return 'reported_by'
    return None


def auto_add_report_to_patrols(application, event):
    field_to_search = which_field_search_for(application)

    if field_to_search:
        subject = getattr(event, field_to_search)

        if subject:
            segments = PatrolSegment.objects.filter(
                leader_id=subject.id, patrol__state=PC_OPEN)
            for segment in segments:
                segment.events.add(event)


class EventSerializer(EventSerializerMixin, rest_framework.serializers.ModelSerializer):

    serializer_choice_field = ChoiceField
    # Using PointField here provides the magic to convert between a
    #  json {lat/lon} and our internal representation.
    location = PointField(required=False, allow_null=True,
                          validators=[PointValidator(), ])
    geometry = EventGeometryField(
        source="geometries", required=False, allow_null=True)
    time = DateTimeField(source='event_time', required=False)
    created_at = DateTimeField(required=False)
    updated_at = DateTimeField(source='sort_at', required=False)
    sort_at = DateTimeField(required=False,)
    created_by_user = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )
    notes = EventNoteSerializer(many=True, required=False)
    reported_by = ReportedByRelatedField(required=False, allow_null=True)
    message = rest_framework.serializers.CharField(
        required=False, allow_blank=True)
    comment = rest_framework.serializers.CharField(
        required=False, allow_blank=True)
    title = rest_framework.serializers.CharField(
        required=False, allow_blank=True)
    # photos = EventPhotoSerializer(many=True, required=False)
    event_type = EventTypeRelatedField(required=False)
    event_details = EventDetailsSerializer(required=False, default={})

    eventsource = EventSourceRelatedField(required=False)

    external_event_id = rest_framework.serializers.CharField(
        max_length=100, required=False)

    contains = rest_framework.serializers.SerializerMethodField()
    is_linked_to = rest_framework.serializers.SerializerMethodField()
    is_contained_in = rest_framework.serializers.SerializerMethodField()

    files = EventFileSerializer(many=True, required=False, read_only=True)

    related_subjects = SubjectSerializer(many=True, required=False)

    patrol_segments = rest_framework.serializers.PrimaryKeyRelatedField(many=True, required=False,
                                                                        queryset=PatrolSegment.objects.all())
    feature_representation = FeatureRepresentation()

    def create(self, validated_data):
        geometries = validated_data.pop("geometries", None)
        instance = super().create(validated_data)

        if geometries:
            self._create_geometries(instance, geometries)

        request = self.context['request']
        if hasattr(request, "auth") and request.auth:
            auto_add_report_to_patrols(request.auth.application, instance)
        return instance

    def update(self, instance, validated_data):
        geometries_exits = "geometries" in validated_data
        geometries = validated_data.pop("geometries", None)
        instance = super().update(instance, validated_data)

        if geometries:
            self._update_latest_geometry(instance, geometries)
        else:
            if geometries_exits:
                self._delete_event_geometries(instance)

        request = self.context["request"]
        if hasattr(request, "auth"):
            auto_add_report_to_patrols(request.auth.application, instance)
        return instance

    def get_contains(self, event):
        self.context["event_relationship_direction"] = "out"
        return self._get_event_relationship(event=event, relationship_name="relationship_out_contains")

    def get_is_linked_to(self, event):
        self.context["event_relationship_direction"] = "out"
        return self._get_event_relationship(event=event, relationship_name="relationship_out_is_linked_to")

    def get_is_contained_in(self, event):
        self.context["event_relationship_direction"] = "in"
        return self._get_event_relationship(event=event, relationship_name="relationship_in_contains")

    def _get_event_relationship(self, event: "Event", relationship_name: str) -> EventRelationshipSerializer:

        if not hasattr(event, f"{relationship_name}"):
            fallback_events_mapping = {
                "relationship_in_contains": "contains",
                "relationship_out_is_linked_to": "is_linked_to",
                "relationship_out_contains": "contains",
            }
            return (
                self.get_in_relation(
                    event=event, value=fallback_events_mapping[relationship_name])
                if relationship_name == "relationship_in_contains"
                else self.get_out_relation(event=event, value=fallback_events_mapping[relationship_name])
            )

        events_mapping = {
            "relationship_in_contains": event.relationship_in_contains,
            "relationship_out_is_linked_to": event.relationship_out_is_linked_to,
            "relationship_out_contains": event.relationship_out_contains,
        }
        return EventRelationshipSerializer(events_mapping[relationship_name], many=True, context=self.context).data

    def validate(self, attrs):
        event_type = attrs.get("event_type")
        event_source = attrs.get("eventsource")
        location = attrs.get("location")
        geometries = attrs.get("geometries")
        end_time = attrs.get("end_time")
        priority = attrs.get("priority")
        state = attrs.get("state")
        external_event_id = attrs.get("external_event_id")

        if event_type and self._is_event_type_geometry(event_type) and location:
            raise ValidationError(
                {"location": "This field is not allowed for events with polygon type."})

        if event_type and self._is_event_type_point(event_type) and geometries:
            raise ValidationError(
                {"geometry": "This field is not allowed for events with point type."})

        if end_time and end_time < self.instance.time:
            raise ValidationError(
                'Event end_time must not be earlier than event time.')

        # For creating an event, if event_type is not present in the request, raise ValidationError.
        if not self.instance:
            if not event_type:
                if event_source and event_source.event_type:
                    attrs["event_type"] = event_source.event_type
                else:
                    raise ValidationError(
                        {"event_type": "Event type must be provided."})

            if self._is_event_source_duplicated(event_source, external_event_id):
                raise DuplicateResourceError(
                    fieldname='external_event_id',
                    detail='External event ID already exists.'
                )

            # Set default priority from event type if not provided in POST.
            if not priority and event_type:
                attrs["priority"] = event_type.default_priority
            if not state and event_type:
                attrs["state"] = event_type.default_state
        return super().validate(attrs)

    def get_out_relation(self, event, value):
        self.context['event_relationship_direction'] = 'out'
        request = self.context.get('request')
        permitted_categories = get_permitted_event_categories(request)

        qs = event.out_relationships.filter(
            to_event__event_type__category__in=permitted_categories,
            type__value=value).all().order_by('ordernum', 'to_event__created_at')

        serializer = EventRelationshipSerializer(
            instance=qs, many=True, context=self.context,)
        return serializer.data

    def get_in_relation(self, event, value):
        qs = event.in_relationships.filter(type__value=value).all()
        self.context['event_relationship_direction'] = 'in'
        serializer = EventRelationshipSerializer(
            instance=qs, many=True, context=self.context,)
        return serializer.data

    class Meta:
        model = activity.models.Event
        read_only_fields = ('updated_at', 'created_at', 'icon_id',)
        default_fields = (
            'id', 'location', 'time', 'end_time', 'serial_number', 'message', 'provenance',
            'event_type', 'priority', 'priority_label', 'attributes', 'comment', 'title',
            'created_by_user', 'notes', 'reported_by',
            'state', 'event_details', 'contains', 'is_linked_to', 'is_contained_in',
            'files', 'related_subjects', 'eventsource', 'external_event_id', 'sort_at',
            'patrol_segments', "geometry")
        fields = (*default_fields, *read_only_fields)

    def __init__(self, *args, **kwargs):
        self._event_geometry_factory = GenericGeometryFactory()

        super().__init__(*args, **kwargs)

        if self.context.get('include_files', True):
            self.fields['files'].context.update(self.context)
        else:
            self.fields.pop('files')

        if self.context.get('include_notes', True):
            self.fields['notes'].context.update(self.context)
        else:
            self.fields.pop('notes')

        if self.context.get('include_details', True):
            self.fields['event_details'].context.update(self.context)
        else:
            self.fields.pop('event_details')

        if not self.context.get('include_related_events', False):
            self.fields.pop('contains')
            self.fields.pop('is_linked_to')

    def to_representation(self, event):
        self.fields.pop('eventsource', None)

        set_prefetched = hasattr(event, 'event_details_set')

        if set_prefetched:
            # pop the following out of the representation if we've prefetched using the _set
            self.fields.pop('event_details', None)
            self.fields.pop('files', None)
            self.fields.pop('related_subjects', None)

        rep = super().to_representation(event)

        details_updates = ""

        if set_prefetched:
            # Apply the prefetched data back to the representation
            try:
                event_details_serialized = EventDetailsSerializer(event.event_details_set, many=True,
                                                                  context=self.context).data
                rep["event_details"] = {}
                if event_details_serialized:
                    rep["event_details"] = event_details_serialized[0]
                rep["files"] = list(EventFileSerializer(
                    event.files_set, many=True, context=self.context).data)
                rep["related_subjects"] = list(SubjectSerializer(
                    event.related_subjects_set, many=True, context=self.context).data)

                event_details = rep["event_details"]
                if event_details:
                    details_updates = event_details.get("updates")
            except Exception as ex:
                logger.exception("Failed Event pre-fetched  {}".format(ex))
        else:
            event_details = rep['event_details']

            if rep['event_details'] is not None:
                details_updates = rep['event_details'].pop('updates')

        try:
            event_source = event.eventsource_event_refs.first().eventsource
        except:
            pass
        else:
            if event_source and event_source.eventprovider:
                rep['external_source'] = {
                    "url": event_source.eventprovider.additional.get('external_event_url'),
                    "text": event_source.eventprovider.display,
                    "icon_url": event_source.eventprovider.additional.get('icon_url')
                }
        if 'request' in self.context:
            request = self.context['request']

            if event.event_type and event.event_type.category:
                category_name = event.event_type.category.value
                rep['event_category'] = category_name
                permission_name = f'activity.{category_name}_read'
                geo_permission_name = f"activity.view_{event.event_type.category.value}_geographic_distance"

                if not request.user.has_perm(permission_name) and not request.user.has_perm(geo_permission_name):
                    rep = {'id': rep['id']}
                    return rep

            rep['url'] = utils.add_base_url(
                request, reverse('event-view', args=[event.id, ]))
            image_url = resolve_image_url(event)
            rep['image_url'] = utils.add_base_url(request, image_url)

            rep["geojson"] = None
            if self._has_instance_feature(event):
                rep["geojson"] = self._get_geojson(request, event)
                if self._has_both_features(event):
                    rep["geojson"] = self._append_point_feature(
                        request, event, rep)

        if event.event_type:
            rep['is_collection'] = event.event_type.is_collection

        # This is to fix https://vulcan.atlassian.net/browse/DAS-6264
        # TODO: Consider adjusting the context within the listed Views.
        if self.context.get('include_updates', True) \
                and not getattr(self.context.get('view', None), 'get_view_name', lambda: None)()\
                in ('Patrols', 'Patrol', 'Patrolsegment'):
            updates = self.render_updates(event)
            for note in rep.get('notes', []):
                updates.extend(note['updates'])
            for f in rep.get('files', []):
                updates.extend(f['updates'])
            if event_details:
                updates.extend(details_updates)
            rep['updates'] = sorted(
                updates, key=lambda u: u['time'], reverse=True)

        patrol_ids = event.patrol_ids if hasattr(event, 'patrol_ids') \
            else activity.models.Event.objects.get_related_patrol_ids(event=event)

        rep['patrols'] = [item for item in patrol_ids if item is not None]

        return rep

    def _has_both_features(self, instance):
        return hasattr(instance, "location") and instance.location and instance.geometries.last()

    def _has_instance_feature(self, instance):
        return hasattr(instance, "location") and instance.location or instance.geometries.last()

    def _get_geojson(self, request, instance):
        if hasattr(instance, "location") and instance.location:
            pass
        elif instance.geometries.last():
            instance = instance.geometries.last()
        return self.feature_representation.get_feature(request, instance)

    def _append_point_feature(self, request, instance, representation):
        geometry_rep = copy.deepcopy(representation.get("geometry", {}))
        geometry_rep["features"].append(
            self.feature_representation.get_feature(request, instance))
        return geometry_rep

    def _create_geometries(self, event: Event, geometry: dict):
        geometry_type = geometry.get("type")

        if geometry_type == "Feature":
            self._create_geometry(event, geometry)
        elif geometry_type == "FeatureCollection":
            for feature in geometry.get("features"):
                self._create_geometry(event, feature)

    def _create_geometry(self, event: Event, geometry: dict):
        sort = geometry.get("geometry", {}).get("type")
        coordinates = geometry.get("geometry").get("coordinates", [[]])[0]
        properties = geometry.get("properties", {})

        event_geometry = self._event_geometry_factory.create_event_geometry(
            sort)
        event_geometry.create(event, coordinates, properties)

    def _update_latest_geometry(self, event: Event, geometry: dict):
        latest_event_geometry = EventGeometry.objects.filter(
            event=event).last()

        if latest_event_geometry:
            feature_type = geometry.get("type")
            if feature_type == "Feature":
                self._update_geometry(geometry, latest_event_geometry)
            elif feature_type == "FeatureCollection":
                for feature in geometry.get("features"):
                    self._update_geometry(feature, latest_event_geometry)
        else:
            self._create_geometries(event, geometry)

    def _update_geometry(self, geometry: dict, event_geometry: EventGeometry):
        coordinates = geometry.get("geometry").get("coordinates")[0]
        properties = geometry.get("properties", {})
        polygon = Polygon(coordinates, srid=4326)
        properties["area"] = get_polygon_info(polygon, "area")
        properties["perimeter"] = get_polygon_info(polygon, "length")

        try:
            event_geometry.properties = properties
            event_geometry.geometry = polygon
            event_geometry.save()
        except Exception as e:
            logger.exception(f"Error {e} trying to update a EventGeometry.")

    def _delete_event_geometries(self, event):
        event.geometries.all().delete()

    def _is_event_type_geometry(self, event_type: EventType):
        return event_type.geometry_type == EventType.GeometryTypesChoices.POLYGON.label

    def _is_event_type_point(self, event_type: EventType):
        return event_type.geometry_type == EventType.GeometryTypesChoices.POINT.label

    def _is_event_source_duplicated(self, event_source, external_event_id):
        return EventsourceEvent.objects.filter(eventsource=event_source, external_event_id=external_event_id).exists()


class EventGeoJsonSerializer(EventSerializer):
    fields_to_copy = ('id', 'event_type', 'serial_number', 'time',
                      'priority', 'priority_label', 'title', 'state',
                      'event_details',
                      'created_at', 'updated_at', 'event_category',
                      'is_collection')

    @classmethod
    def many_init(cls, *args, **kwargs):
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {'child': child_serializer}
        list_kwargs.update(dict([
            (key, value) for key, value in kwargs.items()
            if key in rest_framework.serializers.LIST_SERIALIZER_KWARGS
        ]))
        meta = getattr(cls, 'Meta', None)
        list_serializer_class = getattr(
            meta, 'list_serializer_class', GeoFeatureModelListSerializer)
        return list_serializer_class(*args, **list_kwargs)

    def create(self, validated_data):
        raise NotImplementedError('Create Event using GeoJson not supported')

    def to_representation(self, event):
        rep = super().to_representation(event)
        event_rep = rep.get('geojson')
        if not event_rep:
            if 'request' in self.context:
                event_rep = make_feature(self.context['request'], event)
        if not event_rep:
            event_rep = utils.json.empty_geojson_feature()

        properties = event_rep['properties']

        for name in self.fields_to_copy:
            if name in rep and name not in properties:
                properties[name] = rep[name]

        return event_rep


def make_feature(request, event):
    is_point = isinstance(event.coordinates, Point)
    image_url = resolve_image_url(event)
    image_url = utils.add_base_url(request, image_url)
    feature = utils.json.empty_geojson_feature()
    if event.coordinates:
        feature['geometry'] = {
            'type': 'LineString' if not is_point else 'Point',
            'coordinates': event.coordinates if not is_point else event.coordinates.tuple
        }
    feature['properties'] = {
        'message': event.message,
        'datetime': event.time if isinstance(event.time,
                                             str) else event.time.isoformat(),
        'image': image_url
    }

    properties = feature['properties']
    if image_url:  # hasattr(event, 'image_url'):
        properties['icon'] = {
            "iconUrl": image_url,
            "iconSize": [25, 25],
            "iconAncor": [12, 12],
            "popupAncor": [0, -13],
            "className": 'dot',

        }
    return feature


class EventClassSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = activity.models.EventClass
        fields = ('value', 'display', 'ordernum')


class EventFactorSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = activity.models.EventFactor
        fields = ('value', 'display', 'ordernum')


class EventClassFactorSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = activity.models.EventClassFactor
        fields = ('value',)

    def to_representation(self, instance):
        c = instance.eventclass
        f = instance.eventfactor
        rep = dict(
            value=instance.value,
            class_value=c.value,
            factor_value=f.value,
            priority=instance.priority,
            priority_label=instance.get_priority_display())

        return rep


class EventFilterSpecificationSerializer(rest_framework.serializers.Serializer):

    text = rest_framework.serializers.CharField(
        required=False, allow_blank=True, max_length=100)

    date_range = rest_framework.serializers.DictField(
        required=False, child=rest_framework.serializers.DateTimeField())
    duration = rest_framework.serializers.DurationField(required=False, )
    priority = rest_framework.serializers.ListField(required=False,
                                                    child=rest_framework.serializers.ChoiceField(
                                                        choices=[x[0] for x in activity.models.Event.PRIORITY_CHOICES]))
    state = rest_framework.serializers.ListField(required=False,
                                                 child=rest_framework.serializers.ChoiceField(
                                                     choices=[x[0] for x in activity.models.Event.STATE_CHOICES]))

    event_category = rest_framework.serializers.ListField(
        required=False, child=rest_framework.serializers.CharField())

    event_type = rest_framework.serializers.ListField(
        required=False, child=rest_framework.serializers.CharField())

    reported_by = rest_framework.serializers.ListField(
        required=False, child=rest_framework.serializers.CharField())

    def validate_date_range(self, value):
        if 'lower' in value and 'upper' in value and value['lower'] > value['upper']:
            raise rest_framework.serializers.ValidationError(
                'Invalid date range.')
        return value


class EventFilterSerializer(rest_framework.serializers.ModelSerializer):

    filter_spec = rest_framework.serializers.JSONField()
    filter_name = rest_framework.serializers.CharField()

    class Meta:
        model = activity.models.EventFilter
        fields = ('id', 'filter_name', 'ordernum', 'filter_spec', 'is_hidden')

    def validate_filter_spec(self, attrs):
        EventFilterSpecificationSerializer().run_validation(attrs)
        return super().validate(attrs)

    def create(self, validated_data):
        ef = activity.models.EventFilter.objects.create(**validated_data)
        return ef


class EventProviderSerializer(rest_framework.serializers.ModelSerializer):

    owner = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault())

    class Meta:
        model = activity.models.EventSource
        read_only_fields = ('id', 'owner',)
        fields = read_only_fields + \
            ('display', 'additional', 'is_active',)

    def to_representation(self, obj):
        rep = super().to_representation(obj, )

        rep['owner'] = UserSerializer().to_representation(obj.owner)

        rep['url'] = utils.add_base_url(self.context['request'],
                                        reverse('eventprovider-view',
                                                args=[obj.id]))

        return rep


class EventSourceSerializer(rest_framework.serializers.ModelSerializer):

    event_type = EventTypeRelatedField(required=False, allow_null=True,)

    class Meta:
        model = activity.models.EventSource
        read_only_fields = ('id',)
        fields = read_only_fields + \
            ('eventprovider', 'external_event_type', 'display',
             'event_type', 'additional', 'is_ready',)

    def to_representation(self, obj):
        rep = super().to_representation(obj, )

        rep['url'] = utils.add_base_url(self.context['request'],
                                        reverse('eventsource-view',
                                                args=[obj.id, ]))

        return rep


PHONE_NUMBER_VALIDATOR = RegexValidator(
    regex=r'^\+?1?[-\d]{9,15}$', message="Not a valid phone number.")


class NotificationMethodSerializer(rest_framework.serializers.ModelSerializer):

    owner = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault())

    contact = rest_framework.serializers.DictField()

    class Meta:
        model = activity.models.NotificationMethod
        read_only_fields = ('id', 'owner',)
        fields = ('title', 'contact', 'is_active',) + read_only_fields

    def to_representation(self, instance):

        instance.contact = {'method': instance.method,
                            'value': instance.value}
        rep = super().to_representation(instance)

        rep['owner'] = {
            'username': instance.owner.username
        }

        rep['url'] = utils.add_base_url(self.context['request'],
                                        reverse('notificationmethod-view',
                                                args=[instance.id, ]))
        return rep

    def create(self, validated_data):
        contact = validated_data.pop('contact')
        validated_data['method'] = contact['method']
        validated_data['value'] = contact['value']
        return super().create(validated_data)

    def validate_contact(self, value):

        if value['method'] == 'email':
            try:
                EmailValidator()(value['value'])
            except django.core.exceptions.ValidationError:
                raise ValidationError(
                    {'contact.value': 'Must be a valid email address when using contact.method=\'email\''})

        elif value['method'] == 'sms':
            try:
                PHONE_NUMBER_VALIDATOR(value['value'])
            except django.core.exceptions.ValidationError:
                raise ValidationError(
                    {'contact.value': 'Must be a valid phone number when using contact.method=\'sms\''})

        return value

    def update(self, instance, validated_data):
        contact = validated_data.pop('contact')
        validated_data['method'] = contact['method']
        validated_data['value'] = contact['value']
        return super().update(instance, validated_data)


def _default_schedule():
    return {
        'timezone': timezone.get_current_timezone_name(),
        'periods': {}
    }


class AlertRuleSerializer(rest_framework.serializers.ModelSerializer):
    '''
    Notice that 'notification_methods' and 'notification_method_ids' work together to provide clean read-write
    capabilities in this serializer.

    See: https://stackoverflow.com/questions/29950956/drf-simple-foreign-key-assignment-with-nested-serializers
    '''

    reportTypes = rest_framework.serializers.SlugRelatedField(
        queryset=activity.models.EventType.objects.all(),
        many=True, write_only=False,
        slug_field='value', source='event_types')

    conditions = rest_framework.serializers.JSONField(
        required=False, default=dict)
    schedule = rest_framework.serializers.JSONField(
        required=False, default=_default_schedule)

    owner = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault())

    notification_method_ids = rest_framework.serializers.PrimaryKeyRelatedField(
        queryset=activity.models.NotificationMethod.objects.all(),
        many=True, write_only=False, source='notification_methods')
    # notification_methods = NotificationMethodSerializer(many=True, read_only=True)

    class Meta:
        exclude = ('event_types', 'notification_methods',)
        model = activity.models.AlertRule
        read_only_fields = ('id', 'owner_username',)

    def validate_schedule(self, value):

        try:
            jsonschema.validate(value, OneWeekSchedule.json_schema)

            if not 'timezone' in value:
                value['timezone'] = timezone.get_current_timezone_name()
            else:
                pytz.timezone(value['timezone'])

            return value
        except jsonschema.ValidationError as ve:
            rpath = '/'.join([''] + [str(x) for x in ve.relative_path])
            error_message = f'JSON schema validation error at {rpath}. Value {ve.instance} failed {ve.validator} ' \
                f'validation against {ve.validator_value}'
            raise rest_framework.serializers.ValidationError(error_message)

    def validate_conditions(self, value):
        try:

            # Guardrail: If the request includes an empty array for either
            # conditions-list, then delete it.
            for key in ('all', 'any'):
                if key in value and len(value[key]) < 1:
                    del value[key]

            Conditions(value).validate()
            return value

        except jsonschema.ValidationError as ve:
            rpath = '/'.join([''] + [str(x) for x in ve.relative_path])
            error_message = f'JSON schema validation error at {rpath}. Value {ve.instance} failed {ve.validator} ' \
                f'validation against {ve.validator_value}'
            raise rest_framework.serializers.ValidationError(error_message)

    def to_representation(self, instance):

        rep = super().to_representation(instance)
        rep['owner'] = {
            'username': instance.owner.username
        }

        rep['conditions'].setdefault('all', [])
        rep['conditions'].setdefault('any', [])

        rep['url'] = utils.add_base_url(self.context['request'],
                                        reverse('alert-view',
                                                args=[instance.id, ]))

        return rep

    def update(self, instance, validated_data):

        notification_method_ids = validated_data.pop(
            'notification_method_ids', None)

        if notification_method_ids:
            instance.notification_methods.clear()
            instance.notification_methods.add(*notification_method_ids)

        return super().update(instance, validated_data)


class PatrolTypeSerializer(rest_framework.serializers.ModelSerializer):

    class Meta:
        model = activity.models.PatrolType
        read_only_fields = ('id', 'value', 'display', 'ordernum',
                            'icon_id', 'default_priority', 'is_active')
        fields = read_only_fields


class EventRelatedSegmentSerializer(rest_framework.serializers.ModelSerializer):

    class Meta:
        model = activity.models.EventRelatedSegments
        fields = ('event', 'patrol_segment')
