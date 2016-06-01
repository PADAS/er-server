from collections import OrderedDict

from core.serializers import ContentTypeField
import django.db.models
from django.contrib.auth import get_user_model
from django.utils.encoding import force_text
from django.contrib.gis.geos import Point
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.http import Http404
from drf_extra_fields.geo_fields import PointField
import rest_framework.serializers
from rest_framework.metadata import BaseMetadata
from rest_framework.fields import DateTimeField
from rest_framework.exceptions import ValidationError, APIException
from rest_framework.request import clone_request
from rest_framework.utils.field_mapping import ClassLookupDict

import activity.models
import observations.models
import utils
from accounts.serializers import UserDisplaySerializer, get_username
from observations.serializers import SubjectSerializer, SourceSerializer
from revision.manager import AC_UPDATED


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


class EventJSONSchema(BaseMetadata):
    label_lookup = ClassLookupDict({
        rest_framework.serializers.Field: 'field',
        rest_framework.serializers.BooleanField: 'boolean',
        rest_framework.serializers.NullBooleanField: 'boolean',
        rest_framework.serializers.CharField: 'string',
        rest_framework.serializers.URLField: 'string',
        rest_framework.serializers.EmailField: 'string',
        rest_framework.serializers.RegexField: 'regex',
        rest_framework.serializers.SlugField: 'string',
        rest_framework.serializers.IntegerField: 'integer',
        rest_framework.serializers.FloatField: 'number',
        rest_framework.serializers.DecimalField: 'number',
        rest_framework.serializers.DateField: 'string',
        rest_framework.serializers.DateTimeField: 'string',
        rest_framework.serializers.TimeField: 'string',
        rest_framework.serializers.ChoiceField: 'string',
        rest_framework.serializers.MultipleChoiceField: 'string',
        rest_framework.serializers.FileField: 'file upload',
        rest_framework.serializers.ImageField: 'image upload',
        rest_framework.serializers.ListField: 'array',
        rest_framework.serializers.DictField: 'object',
        rest_framework.serializers.Serializer: 'object',
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
                if isinstance(field, (rest_framework.serializers.PrimaryKeyRelatedField,)):
                    continue
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
        field_info['type'] = self.label_lookup[field]
        field_info['id'] = field
        field_info['required'] = getattr(field, 'required', False)

        attrs = [
            'read_only', 'label', 'help_text',
            'min_length', 'max_length',
            'min_value', 'max_value'
        ]

        for attr in attrs:
            value = getattr(field, attr, None)
            if value is not None and value != '':
                field_info[attr] = force_text(value, strings_only=True)

        if getattr(field, 'child', None):
            field_info['child'] = self.get_field_info(field.child)
        elif getattr(field, 'fields', None):
            field_info['children'] = self.get_serializer_info(field)

        if not field_info.get('read_only'):
            if hasattr(field, 'object_choices'):
                field_info['oneOf'] = [
                    {
                        choice_value: force_text(choice_name, strings_only=True)
                    }
                    for choice_value, choice_name in field.object_choices
                    ]
            elif hasattr(field, 'choices'):
                field_info['oneOf'] = [
                    {
                        choice_value: force_text(choice_name, strings_only=True)
                    }
                    for choice_value, choice_name in field.choices.items()
                    ]

        return field_info


class ReportedByRelatedField(rest_framework.serializers.RelatedField):
    def to_representation(self, value):
        mapping = REPORTED_SERIALIZER_MAPPING.get(
            value._meta.label_lower, None)
        if not mapping:
            raise Exception('Unexpected ReportedBy Type {0}'.format(type(value)))

        return mapping['serializer']().to_representation(value)

    def get_queryset(self):
        for obj in observations.models.Subject.objects.get_staff():
            yield obj
        for obj in get_user_model().objects.all().filter(is_active=True):
            yield obj
        for obj in activity.models.Community.objects.all():
            yield obj

    def to_internal_value(self, data):
        mapping = REPORTED_SERIALIZER_MAPPING.get(
            data['content_type'], None)
        if not mapping:
            raise Exception(
                'Unexpected ReportedBy Type {0}'.format(data))

        return mapping['serializer']().to_internal_value(data)

    @property
    def object_choices(self):
        queryset = self.get_queryset()
        if queryset is None:
            # Ensure that field.choices returns something sensible
            # even when accessed with a read-only field.
            return {}

        return [(self.to_representation(item),
                 self.display_value(item))
                 for item in queryset]


class AttachmentRelatedField(rest_framework.serializers.RelatedField):
    def to_representation(self, value):
        mapping = ATTACHMENT_SERIALIZER_MAPPING.get(
            value._meta.label_lower, None)
        if not mapping:
            raise Exception('Unexpected Attachment Type {0}'.format(type(value)))

        return mapping['serializer']().to_representation(value)


class EventAttachmentSerializer(rest_framework.serializers.ModelSerializer):
    target = AttachmentRelatedField(read_only=True)

    class Meta:
        model = activity.models.EventAttachment
        fields = ('target', 'reason', 'id')


class EventNoteSerializer(rest_framework.serializers.ModelSerializer):
    created_by_user = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )

    class Meta:
        model = activity.models.EventNote
        read_only_fields = ('created_at',)
        write_only_fields = ('event',)
        fields = ('id', 'created_by_user', 'text') + write_only_fields + read_only_fields

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
                user=get_username(revision.user)),
                time=revision.revision_at.isoformat(),
                text=revision.data.get('text', ''),
                user=UserDisplaySerializer().to_representation(revision.user)
            )
            for revision in note.revision.all()
        ]


class EventSerializer(rest_framework.serializers.ModelSerializer):
    # Using PointField here provides the magic to convert between a
    #  json {lat/lon} and our internal representation.
    location = PointField(required=False)
    time = DateTimeField(source='event_time')
    created_by_user = rest_framework.serializers.HiddenField(
        default=rest_framework.serializers.CurrentUserDefault()
    )
    notes = EventNoteSerializer(many=True, required=False)
    reported_by = ReportedByRelatedField()

    class Meta:
        model = activity.models.Event
        fields = (
            'id', 'location', 'time', 'message', 'provenance',
            'event_type', 'priority', 'priority_label', 'attributes',
            'image_url', 'created_by_user', 'notes', 'reported_by')

    def create(self, validated_data):
        return activity.models.Event.objects.create_event(**validated_data)

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance

    def to_internal_value(self, data):
        obj = super().to_internal_value(data)
        return obj

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
                rep['subject'] = SubjectSerializer().to_representation(subject_attachment.target)
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
        rep['updates'] = sorted(updates, key=lambda u: u['time'], reverse=True)
        return rep

    def render_updates(self, event):
        def get_action(revision):
            if revision.action == AC_UPDATED:
                field_mapping = {'message': 'Event Text',
                                 'event_time': 'Event Time',
                                 'priority': 'Event Priority',
                                 'location': 'Location',
                                 'provenance': 'Event Reporter',
                                 'created_by_user': 'Event Writer'}
                fieldnames = [field_mapping[k] for k in revision.data.keys() if k in field_mapping]
                return '{0} fields: {1}'.format(revision.get_action_display(),
                                                ', '.join(fieldnames))
            return revision.get_action_display()

        return [dict(message='Event {action} by {user}'.format(
            action=get_action(revision),
            user=get_username(revision.user)
        ), time=revision.revision_at.isoformat(),
           user=UserDisplaySerializer().to_representation(revision.user))
                for revision in event.revision.all()
                ]


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
        'datetime': event.time if isinstance(event.time, str) else event.time.isoformat(),
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
