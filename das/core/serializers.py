from collections import OrderedDict

import django.contrib.gis.serializers.geojson as geojson
import rest_framework.serializers as serializers
from django.contrib.contenttypes.models import ContentType
from rest_framework.fields import empty

from activity.models import Community, Event
from observations.models import Subject


class ContentTypeField(serializers.Field):
    def to_representation(self, value):
        return value._meta.label_lower

    def to_internal_value(self, data):
        app_label, model = data.split('.')
        return ContentType.objects.get(app_label=app_label, model=model)

    def get_attribute(self, obj):
        # We pass the object instance onto `to_representation`,
        # not just the field attribute.
        return obj

    def get_value(self, dictionary):
        return dictionary.get(self.field_name)


class Serializer(geojson.Serializer):
    def get_dump_object(self, obj):
        property_map = self.options.get('properties', None)

        if property_map:
            for name, new_name in property_map.items():
                if name in self._current:
                    self._current[new_name] = self._current[name]
                    del self._current[name]
                elif hasattr(obj, name):
                    self._current[new_name] = getattr(obj, name)

        field_name = 'presentation'
        if field_name in self._current:
            self._current.update(self._current[field_name])
            del self._current[field_name]

        image_url = self._current.pop('image_url', None)
        if image_url:
            self._current['icon'] = {
                "iconUrl": image_url,
                "iconSize": [25, 25],
                "iconAncor": [12, 12],
                "popupAncor": [0, -13],
                "className": 'dot',

            }

        return super().get_dump_object(obj)

    def end_object(self, obj):
        self.json_kwargs.pop('properties', None)
        return super().end_object(obj)


class TimestampMixin:
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class GenericRelatedField(serializers.RelatedField):
    def get_field_mapping(self, label=None):
        from observations.serializers import SubjectSerializer
        from accounts.serializers import UserDisplaySerializer
        from activity.serializers import CommunitySerializer

        default_mapping = {
            'observations.subject': {'serializer': SubjectSerializer,
                                     'field': 'subject'},
            'accounts.user': {'serializer': UserDisplaySerializer,
                              'field': 'user'},
            'activity.community': {'serializer': CommunitySerializer,
                                   'field': 'community'}
        }
        return default_mapping, label

    def to_representation(self, value):

        field_mapping, label = self.get_field_mapping()
        mapping = field_mapping.get(
            value._meta.label_lower, None)
        if not mapping:
            raise Exception(f'Unexpected {label} Type {type(value)}')

        return mapping['serializer']().to_representation(value)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            content_type_value = data['content_type']
        else:
            content_type_value = data._meta.label_lower
            data = {"id": data.id, "content_type": content_type_value}

        field_mapping, label = self.get_field_mapping()
        mapping = field_mapping.get(content_type_value, None)
        if not mapping:
            raise Exception(f'Unexpected {label} Type {data}')

        return mapping['serializer']().to_internal_value(data)

    def get_queryset(self):
        return Community.objects.all()

    def run_validation(self, data=empty):
        # We force empty strings & empty dictionary to None values for
        # relational fields.
        if data == '' or data == {}:
            data = None
        return super().run_validation(data)

    def get_object_queryset(self):
        request = self.context.get('request')
        for p in Event.PROVENANCE_CHOICES:
            provenance = p[0]
            values = list(
                Event.objects.get_reported_by_for_provenance(
                    provenance, request.user))
            if values:
                yield (provenance, values)

    def display_value(self, instance):
        from accounts.serializers import get_user_display, get_user_model
        from observations.serializers import get_subject_display

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

    def is_allowed_to_view(self, output):
        request = self.context.get('request')

        if output.get('content_type') == 'observations.subject':
            subject_id = output.get('id')
            return Subject.objects.filter(id=subject_id).by_user_subjects(request.user)
        return True


class PointValidator:
    """Check that the point field is valid in the latitude and longitude values
    we do this by checking Point.valid is True"""

    def __call__(self, value):
        if value is None:
            raise serializers.ValidationError("Location value is empty")
        if not value.valid:
            raise serializers.ValidationError(value.valid_reason)
