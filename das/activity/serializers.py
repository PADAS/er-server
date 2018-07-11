import logging
import traceback
import copy
from collections import OrderedDict

from core.serializers import ContentTypeField
from core.utils import static_image_finder

from choices.serializers import ChoiceField
from django.utils.encoding import force_text
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from django.http import Http404

from django.contrib.contenttypes.models import ContentType
from django.db.models import ForeignKey

from drf_extra_fields.geo_fields import PointField
import drf_extra_fields.geo_fields
import rest_framework.serializers
import rest_framework.status
from rest_framework.metadata import BaseMetadata
from rest_framework.fields import DateTimeField
from rest_framework.exceptions import ValidationError, APIException
from django.utils.encoding import force_text
from rest_framework.request import clone_request
from rest_framework.utils.field_mapping import ClassLookupDict
from versatileimagefield.serializers import VersatileImageFieldSerializer
import versatileimagefield.files

# Make dictionaries from the IMAGE_SETS, to make lookups a little easier.
from versatileimagefield.utils import get_resized_path, get_rendition_key_set, IMAGE_SETS
IMAGE_RENDITION_SETS = dict((k, dict(v)) for k, v in IMAGE_SETS.items())

import jsonschema
import jsonschema.exceptions
from utils.json import loads
from utils.drf import PointValidator
import activity.models
import utils
from accounts.serializers import UserDisplaySerializer, get_user_display, UserSerializer
from observations.serializers import SubjectSerializer, SourceSerializer, get_subject_display
from observations.models import Subject
from analyzers.serializers import SubjectAnalyzerResultSerializer
from revision.manager import AC_UPDATED, AC_RELATION_DELETED

import utils.schema_utils as schema_utils
from activity.models import EventRelationship
import usercontent.serializers


class DuplicateResourceError(APIException):
    default_status_code = rest_framework.status.HTTP_409_CONFLICT
    default_fieldname = 'unknown field'
    default_detail = 'The resource provided conflicts with an existing resource.'

    def __init__(self, fieldname=None, detail=None, status_code=None):

        self.status_code = status_code or self.default_status_code

        self.detail = {
            fieldname or self.default_fieldname: force_text(detail or self.default_detail)
        }

# class CustomValidation(APIException):
#     status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
#     default_detail = 'A server error occurred.'
#
#     def __init__(self, detail, field, status_code):
#         if status_code is not None:self.status_code = status_code
#         if detail is not None:
#             self.detail = {field: force_text(detail)}
#         else: self.detail = {'detail': force_text(self.default_detail)}


logger = logging.getLogger(__name__)


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


REPORTED_SERIALIZER_MAPPING = {
    'observations.subject': {'serializer': SubjectSerializer,
                             'field': 'subject'},
    'accounts.user': {'serializer': UserDisplaySerializer,
                      'field': 'user'},
    'activity.community': {'serializer': CommunitySerializer,
                           'field': 'community'},

}


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

        if not field_info.get('read_only'):
            if hasattr(field, 'object_choices'):
                object_choices = field.object_choices
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
                                    'title': force_text(choice_name,
                                                        strings_only=True)
                                }
                                for choice_value, choice_name in filter_blank_choice(values_iter)
                            ]
                        else:
                            unassigned.append({
                                'value': group,
                                'title': force_text(values,
                                                    strings_only=True)
                            })
                    if not enum_ext:
                        enum_ext = unassigned
                else:
                    enum_ext = [
                        {
                            'value': choice_value,
                            'title': force_text(choice_name, strings_only=True)
                        }
                        for choice_value, choice_name in filter_blank_choice(field.object_choices)
                    ]
                    field_info['enum'] = [v['value'] for v in
                                          enum_ext]
                field_info['enum_ext'] = enum_ext
            elif hasattr(field, 'choices'):
                field_info['enum_ext'] = [
                    {
                        'value': choice_value,
                        'title': force_text(choice_name, strings_only=True)
                    }
                    for choice_value, choice_name in filter_blank_choice(field.choices)
                ]
                field_info['enum'] = [v['value'] for v in
                                      field_info['enum_ext']]

        return field_info


class ReportedByRelatedField(rest_framework.serializers.RelatedField):
    def to_representation(self, value):
        mapping = REPORTED_SERIALIZER_MAPPING.get(
            value._meta.label_lower, None)
        if not mapping:
            raise Exception(
                'Unexpected ReportedBy Type {0}'.format(type(value)))

        return mapping['serializer']().to_representation(value)

    def to_internal_value(self, data):
        mapping = REPORTED_SERIALIZER_MAPPING.get(
            data['content_type'], None)
        if not mapping:
            raise Exception(
                'Unexpected ReportedBy Type {0}'.format(data))

        return mapping['serializer']().to_internal_value(data)

    def get_queryset(self):
        return activity.models.Community.objects.all()

    def get_object_queryset(self):
        for p in activity.models.Event.PROVENANCE_CHOICES:
            provenance = p[0]
            values = list(
                activity.models.Event.objects.get_reported_by_for_provenance(
                    provenance))
            if values:
                yield (provenance, values)

    def display_value(self, instance):
        if isinstance(instance, get_user_model()):
            return get_user_display(instance)
        elif isinstance(instance, Subject):
            return get_subject_display(instance)
        return super().display_value(instance)

    def get_choices(self, cutoff=None):
        '''get_choices does not work for this complicated field, see object_choices'''
        return OrderedDict()

    @property
    def object_choices(self):
        queryset = self.get_object_queryset()
        if queryset is None:
            # Ensure that field.choices returns something sensible
            # even when accessed with a read-only field.
            return {}
        choices = []
        for provenance, values in queryset:
            choices += [(self.to_representation(item), self.display_value(item))
                        for item in values]
        return choices


class EventTypeRelatedField(rest_framework.serializers.RelatedField):
    def get_queryset(self):
        return activity.models.EventType.objects.all_sort()

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


class ExternalEventTypeRelatedField(rest_framework.serializers.RelatedField):

    def get_queryset(self):
        user = self.context['request'].user
        return activity.models.EventSource.objects.filter(owner=user)

    def to_representation(self, value):
        return value.external_event_type if value else None

    def to_internal_value(self, data):

        if data:
            try:
                user = self.context['request'].user
            except AttributeError:
                pass
            else:
                try:
                    return activity.models.EventSource.objects.get(owner=user, external_event_type=data)
                except activity.models.EventSource.DoesNotExist:
                    raise rest_framework.serializers.ValidationError(
                        {'external_event_type': 'Value \'%s\' does not exist.' % data})
        return None

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display)
                            for row in self.get_queryset()))


class EventCategorySerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = activity.models.EventCategory
        read_only_fields = ('value', 'display', 'ordernum', 'flag',)
        fields = read_only_fields

    def to_representation(self, obj):
        rep = super().to_representation(obj)

        # If we know the user requesting the category, include their permissions
        # for that category
        user = getattr(self.context.get('request', None), 'user', None)
        if user is not None:
            rep['permissions'] = self.get_allowed_actions_for_category(
                user, rep['value'])
        return rep

    def get_allowed_actions_for_category(self, user, category_name):
        allowed_actions = []
        for action in ('create', 'update', 'read', 'delete'):
            if user.has_perm('activity.{0}_{1}'.format(category_name, action)):
                allowed_actions.append(action)
        return allowed_actions


class EventTypeSerializer(rest_framework.serializers.ModelSerializer):
    category = EventCategorySerializer(read_only=True)

    class Meta:
        model = activity.models.EventType
        read_only_fields = ('value', 'display', 'ordernum',
                            'is_collection', 'category', 'icon', 'default_priority',)
        fields = read_only_fields

    def to_representation(self, obj):
        rep = super().to_representation(obj, )
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
            dict(message='Note {action} by {user}'.format(
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
            dict(message='Photo {action} by {user}'.format(
                action=get_action(revision),
                user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get('text', ''),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=get_update_type(revision),
            )
            for revision in photo.revision.all_user()
        ]


class EventFileSerializer(rest_framework.serializers.ModelSerializer):

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

    def create(self, validated_data):

        # Get uploaded file from request.
        ser = usercontent.serializers.UserContentSerializer(
            data=dict(file=self.context['request'].data['filecontent.file'],
                      ),
            context={'request': self.context['request']})

        ser.is_valid(raise_exception=True)
        filecontent = ser.create(ser.validated_data)

        validated_data.pop('filecontent.file', None)

        validated_data['usercontent'] = filecontent

        return super().create(validated_data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        rep['updates'] = self.render_updates(instance)

        if 'request' in self.context:
            request = self.context['request']
            rep['url'] = utils.add_base_url(request,
                                            reverse('event-view-file',
                                                    args=[instance.event.id, instance.id, ]))

            # If attached usercontent is an ImageFileField, then render urls
            # for renditions.
            if isinstance(instance.usercontent.file, (versatileimagefield.files.VersatileImageFieldFile,)):

                # Image Sizes
                image_sizes = {}
                # '('thumbnail', 'large'):
                for size in IMAGE_RENDITION_SETS['default'].keys():
                    image_sizes[size] = utils.add_base_url(request,
                                                           reverse('event-view-file-size',
                                                                   args=[instance.event.id, instance.id,
                                                                         size, instance.usercontent.filename]))
                if image_sizes:
                    rep['images'] = image_sizes

        # Promote some usercontent attributes.
        rep['filename'] = rep['usercontent'].get('filename')
        rep['file_type'] = rep['usercontent'].get('file_type')

        try:
            rep['icon_url'] = rep['images']['icon']
        except KeyError:
            rep['icon_url'] = rep['usercontent'].get('icon_url')

        # Prune some unnecessary attributes.
        for att in ('usercontent', 'event', 'usercontent_id', 'usercontent_type'):
            rep.pop(att, default=None)

        return rep

    def render_updates(self, event_file):
        def get_action(revision):
            return revision.get_action_display()

        return [
            dict(message='File {action} by {user}'.format(
                action=get_action(revision),
                user=get_user_display(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get('text', ''),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=get_update_type(revision),
            )
            for revision in event_file.revision.all_user()
        ]

    def is_valid(self, raise_exception=False):

        try:
            r = super().is_valid(raise_exception=raise_exception)
        except Exception as e:
            raise e
        return r


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
                **{'event': instance, 'data': validated_data})

        elif current_details.data != validated_data:
            current_details.data = validated_data
            current_details.save()

        return current_details

    def _to_internal_value_inner(self, instance, data):

        if instance is None:
            data['_internal_validated'] = False
            return data

        event_type = instance.event_type
        if 'request' in self.context and 'event_type' in self.context['request'].data:
            new_event_type = self.context['request'].data['event_type']
            if new_event_type and new_event_type != instance.event_type.value:
                event_type = activity.models.EventType.objects.get(
                    value=new_event_type)

        schema = event_type.schema

        if not schema:
            return super().to_internal_value(data)

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
                    matches = [d for d in parameters[k] if d['value'] == value]
                    if len(matches) > 0:
                        all_values.append(matches[0])
                if len(all_values) > 0:
                    ret[k] = all_values
            elif type(v) == str and k in parameters and v in parameters[k]:
                ret[k] = {'name': parameters[k][v], 'value': v}
            else:
                ret[k] = v
        return ret

    def to_internal_value(self, data):
        return self._to_internal_value_inner(self.root.instance, data)

    def to_representation(self, event_details):
        if not event_details:
            return OrderedDict()
        ret = OrderedDict(event_details.data['event_details'])
        return ret

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

        external_event_type = validated_data.pop('external_event_type', None)
        external_event_id = validated_data.pop('external_event_id', None)

        new_event = activity.models.Event.objects.create_event(
            **validated_data)

        EventDetailsSerializer().update(new_event, details_data)

        if external_event_type and external_event_id:
            try:
                activity.models.EventsourceEvent.objects.add_relation(new_event,
                                                                      external_event_type, external_event_id)
            except Exception as e:
                raise

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
        update_fields = []
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
        revisions = list(iter(event.revision.all_user().order_by('sequence')))
        while revisions:
            revision = revisions.pop()
            record = dict(
                message='{action} by {user}'.format(
                    action=get_action(revision),
                    user=self.get_user_display(revision.user, event)
                ),
                time=revision.revision_at.isoformat(),
                user=self.get_revision_user(revision.user, event),
                type=get_update_type(revision, revisions))
            if record['type'] in ('read',):
                continue
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

    class Meta:
        model = activity.models.Event
        fields = ('id', 'message', 'time', 'end_time',
                  'serial_number', 'priority', 'event_type', 'icon_id',)

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


class EventSerializer(EventSerializerMixin, rest_framework.serializers.ModelSerializer):
    serializer_choice_field = ChoiceField
    # Using PointField here provides the magic to convert between a
    #  json {lat/lon} and our internal representation.
    location = PointField(required=False, validators=[PointValidator(), ])
    time = DateTimeField(source='event_time', required=False)
    created_at = DateTimeField(required=False)
    updated_at = DateTimeField(source='sort_at', required=False)
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

    external_event_type = ExternalEventTypeRelatedField(required=False)
    external_event_id = rest_framework.serializers.CharField(
        max_length=100, required=False)

    contains = rest_framework.serializers.SerializerMethodField()
    is_linked_to = rest_framework.serializers.SerializerMethodField()
    is_contained_in = rest_framework.serializers.SerializerMethodField()

    files = EventFileSerializer(many=True, required=False, read_only=True)

    related_subjects = SubjectSerializer(many=True, required=False)

    def get_contains(self, event):
        return self.get_out_relation(event, 'contains')

    def get_is_linked_to(self, event):
        return self.get_out_relation(event, 'is_linked_to')

    def get_is_contained_in(self, event):
        return self.get_in_relation(event, 'contains')

    def validate(self, attrs):

        end_time = attrs.get('end_time')
        if end_time is not None and end_time < self.instance.time:
            raise rest_framework.serializers.ValidationError(
                'Event end_time must not be earlier than event time.')

        # If we're creating an event, and event_type is not present in the
        # request, raise ValidationError.

        if self.instance is None:
            event_type = attrs.get('event_type')
            if event_type is None:
                external_event_type = attrs.get('external_event_type')
                if external_event_type:
                    event_type = external_event_type.event_type

                if activity.models.EventsourceEvent.objects.filter(eventsource=external_event_type,
                                                                   external_event_id=attrs.get('external_event_id')).exists():
                    error = DuplicateResourceError(
                        fieldname='external_event_id', detail='External event ID already exists.'
                    )
                    raise error
            if not event_type:
                raise rest_framework.serializers.ValidationError(
                    {'event_type': 'Event type must be provided.'})
            else:
                attrs['event_type'] = event_type

        # Default priority from Event-Type if it's not provided in POST.
        if self.instance is None:
            if attrs.get('priority') is None:
                attrs['priority'] = attrs['event_type'].default_priority

        return super().validate(attrs)

    def get_out_relation(self, event, value):
        self.context['event_relationship_direction'] = 'out'
        qs = event.out_relationships.filter(
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
        fields = (
            'id', 'location', 'time', 'end_time', 'serial_number', 'message', 'provenance',
            'event_type', 'priority', 'priority_label', 'attributes', 'comment', 'title',
            'created_by_user', 'notes', 'reported_by',
            'state', 'event_details', 'contains', 'is_linked_to', 'is_contained_in',
            'files', 'related_subjects', 'external_event_type', 'external_event_id') + read_only_fields

    def __init__(self, *args, **kwargs):
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
        self.fields.pop('external_event_type', None)
        rep = super().to_representation(event)
        if 'request' in self.context:
            request = self.context['request']

            if event.event_type and event.event_type.category:
                rep['event_category'] = event.event_type.category.value
                permission_name = 'activity.{0}_read'.format(
                    event.event_type.category.value)
                if not request.user.has_perm(permission_name):
                    return []

            rep['url'] = utils.add_base_url(request,
                                            reverse('event-view',
                                                    args=[event.id, ]))
            image_url = resolve_image_url(event)
            rep['image_url'] = utils.add_base_url(request, image_url)

            if event.location is not None:
                geodata = make_feature(self.context['request'], event)
                rep['geojson'] = geodata

        if self.context.get('include_updates', True):
            updates = self.render_updates(event)
            for note in rep.get('notes', []):
                updates.extend(note['updates'])
            for f in rep.get('files', []):
                updates.extend(f['updates'])
            rep['updates'] = sorted(
                updates, key=lambda u: u['time'], reverse=True)

        if event.event_type:
            rep['is_collection'] = event.event_type.is_collection

        return rep


def make_feature(request, event):
    is_point = isinstance(event.coordinates, Point)
    image_url = resolve_image_url(event)
    image_url = utils.add_base_url(request, image_url)
    feature = utils.json.empty_geojson_feature()
    feature['geometry'] = {
        'type': 'LineString' if not is_point else 'Point',
        'coordinates': event.coordinates if not is_point else event.coordinates.tuple
    }
    feature['type'] = 'Feature'
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


class EventSourceSerializer(rest_framework.serializers.ModelSerializer):

    owner = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault())
    event_type = EventTypeRelatedField(required=False, allow_null=True,)

    class Meta:
        model = activity.models.EventSource
        read_only_fields = ('id', 'owner',)
        fields = read_only_fields + \
            ('external_event_type', 'display',
             'event_type', 'additional', 'is_ready',)

    def to_representation(self, obj):
        rep = super().to_representation(obj, )

        rep['owner'] = UserSerializer().to_representation(obj.owner)

        rep['url'] = utils.add_base_url(self.context['request'],
                                        reverse('eventsource-view',
                                                args=[obj.external_event_type]))

        return rep
