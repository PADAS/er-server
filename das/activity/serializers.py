import logging
from collections import OrderedDict

from core.serializers import ContentTypeField, ChoiceField
from django.utils.encoding import force_text
from django.contrib.gis.geos import Point
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from django.http import Http404
from drf_extra_fields.geo_fields import PointField
import drf_extra_fields.geo_fields
import rest_framework.serializers
from rest_framework.metadata import BaseMetadata
from rest_framework.fields import DateTimeField, IntegerField
from rest_framework.exceptions import ValidationError, APIException
from rest_framework.request import clone_request
from rest_framework.utils.field_mapping import ClassLookupDict
from versatileimagefield.serializers import VersatileImageFieldSerializer

import activity.models
import utils
from accounts.serializers import UserDisplaySerializer, get_user_display
from observations.serializers import SubjectSerializer, SourceSerializer
from revision.manager import AC_UPDATED

logger = logging.getLogger(__name__)


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


ATTACHMENT_SERIALIZER_MAPPING = {
    'observations.subject': {'serializer': SubjectSerializer,
                             'field': 'subject'},
    'observations.source': {'serializer': SourceSerializer,
                            'field': 'source'},
}

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
        yield value,display

class EventJSONSchema(BaseMetadata):
    label_lookup = ClassLookupDict({
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
        rest_framework.serializers.ChoiceField: 'string',
        rest_framework.serializers.MultipleChoiceField: 'string',
        rest_framework.serializers.ListField: 'array',
        rest_framework.serializers.DictField: 'object',
        rest_framework.serializers.Serializer: 'object',
        rest_framework.serializers.UUIDField: 'string',
        rest_framework.serializers.RelatedField: 'object',
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
        metadata['description'] = view.get_view_description()
        if hasattr(view, 'get_serializer'):
            properties = self.determine_properties(request, view)
            metadata['properties'] = properties

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
                # appropriate metadata about the fields that should be supplied.
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
        return super().display_value(instance)

    @property
    def object_choices(self):
        queryset = self.get_object_queryset()
        if queryset is None:
            # Ensure that field.choices returns something sensible
            # even when accessed with a read-only field.
            return {}

        return {provenance: [(
                                 self.to_representation(item),
                                 self.display_value(item)) for item in values]
                for provenance, values in queryset}


class AttachmentRelatedField(rest_framework.serializers.RelatedField):
    def to_representation(self, value):
        mapping = ATTACHMENT_SERIALIZER_MAPPING.get(
            value._meta.label_lower, None)
        if not mapping:
            raise Exception(
                'Unexpected Attachment Type {0}'.format(type(value)))

        return mapping['serializer']().to_representation(value)


class EventTypeRelatedField(rest_framework.serializers.RelatedField):
    def get_queryset(self):
        return activity.models.EventType.objects.all_sort()

    def to_representation(self, value):
        return value.value

    def to_internal_value(self, data):
        if data:
            return activity.models.EventType.objects.get_by_value(data)
        return None

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display)
                            for row in self.get_queryset()))


class EventAttachmentSerializer(rest_framework.serializers.ModelSerializer):
    target = AttachmentRelatedField(read_only=True)

    class Meta:
        model = activity.models.EventAttachment
        fields = ('target', 'reason', 'id')


def get_update_type(revision, previous_revisions=[]):
    field_mapping = (('location','update_location'), ('message','update_message'),
                     ('event_time','update_datetime'), ('reported_by', 'update_reported_by'),
                     ('state', 'update_event_state'), ('priority', 'update_event_priority'),
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
            for row in previous_revisions:
                if row.data.get('state', None):
                    if row.data.get('state') == activity.models.Event.SC_RESOLVED:
                        return 'unresolved'
                    break

        for k, v in field_mapping:
            if data.get(k, None):
                return v
    return 'other'



class EventNoteSerializer(rest_framework.serializers.ModelSerializer):
    created_by_user = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )

    class Meta:
        model = activity.models.EventNote
        read_only_fields = ('created_at', 'updated_at')
        write_only_fields = ('event',)
        fields = ('id', 'created_by_user',
                  'text') + write_only_fields + read_only_fields

    def create(self, validated_data):
        return activity.models.EventNote.objects.create_note(**validated_data)

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance

    def to_representation(self, note):
        rep = super().to_representation(note)
        rep['updates'] = self.render_updates(note)
        return rep

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
            for revision in note.revision.all()
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
        read_only_fields = ('created_at', 'updated_at')
        write_only_fields = ('event',)
        fields = ('id', 'created_by_user',
                  'image') + write_only_fields + read_only_fields

    def to_representation(self, photo):
        rep = super().to_representation(photo)
        rep['updates'] = self.render_updates(photo)
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
            for revision in photo.revision.all()
            ]


class EventSerializer(rest_framework.serializers.ModelSerializer):
    serializer_choice_field = ChoiceField
    # Using PointField here provides the magic to convert between a
    #  json {lat/lon} and our internal representation.
    location = PointField(required=False)
    time = DateTimeField(source='event_time', required=False)
    updated_at = DateTimeField(source='sort_at', required=False)
    created_by_user = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )
    notes = EventNoteSerializer(many=True, required=False)
    reported_by = ReportedByRelatedField(required=False)
    message = rest_framework.serializers.CharField(required=True)
    photos = EventPhotoSerializer(many=True, required=False)
    event_type = EventTypeRelatedField()

    class Meta:
        model = activity.models.Event
        read_only_fields = ('updated_at',)
        fields = (
            'id', 'location', 'time', 'message', 'provenance',
            'event_type', 'priority', 'priority_label', 'attributes',
            'image_url', 'created_by_user', 'notes', 'reported_by',
            'state', 'photos') + read_only_fields

    def create(self, validated_data):
        return activity.models.Event.objects.create_event(**validated_data)

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance

    def to_representation(self, event):
        rep = super().to_representation(event)
        rep['url'] = utils.add_base_url(self.context['request'],
                                        reverse('event-view',
                                                args=[event.id, ]))

        if event.location is not None:
            geodata = make_feature(self.context['request'], event)
            rep['geojson'] = geodata

        subject_attachment = event.attachments.filter(reason='target')

        if subject_attachment:
            try:
                # TODO: Fix this so it can handle different types of attachments.
                subject_attachment = subject_attachment[0]
                rep['subject'] = SubjectSerializer().to_representation(
                    subject_attachment.target)
            except:
                pass

        attachments = []
        for attach in event.attachments.all():
            attachments.append(EventAttachmentSerializer()
                               .to_representation(attach))

        if attachments:
            rep['attachments'] = attachments

        updates = self.render_updates(event)
        for note in rep['notes']:
            updates.extend(note['updates'])
        for photo in rep['photos']:
            updates.extend(photo['updates'])
        rep['updates'] = sorted(updates, key=lambda u: u['time'], reverse=True)
        return rep

    def render_updates(self, event):
        def get_action(revision):
            if revision.action == AC_UPDATED:
                field_mapping = {'message': 'Event Message',
                                 'event_time': 'Event Time',
                                 'state': 'Event State is {0}',
                                 'priority': 'Event Priority is {0}',
                                 'location': 'Location',
                                 'provenance': 'Event Reporter',
                                 'event_type': 'Event Type is {0}',
                                 'created_by_user': 'Event Writer',}
                fieldnames = [field_mapping[k].format(event.get_display_value(k, v)) for k, v in revision.data.items() if
                              k in field_mapping]
                return '{0} fields: {1}'.format(revision.get_action_display(),
                                                ', '.join(fieldnames))
            return revision.get_action_display()

        result = []
        revisions = [v for v in event.revision.all()]
        while revisions:
            revision = revisions.pop()
            result.append(dict(message='Event {action} by {user}'.format(
            action=get_action(revision),
            user=self.get_user_display(revision.user, event)
        ), time=revision.revision_at.isoformat(),
            user=self.get_revision_user(revision.user, event),
            type=get_update_type(revision, revisions))
            )
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


def make_feature(request, event):
    is_point = isinstance(event.coordinates, Point)
    image_url = utils.add_base_url(request, event.image_url)
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
        'image': event.image_url
    }

    properties = feature['properties']
    if hasattr(event, 'image_url'):
        properties['icon'] = {
            "iconUrl": image_url,
            "iconSize": [25, 25],
            "iconAncor": [12, 12],
            "popupAncor": [0, -13],
            "className": 'dot',

        }
    return feature
