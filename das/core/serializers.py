import rest_framework.serializers as serializers
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from django.utils import six
import django.contrib.gis.serializers.geojson as geojson


class ChoiceField(serializers.Field):
    default_error_messages = {
        'invalid_choice': _('"{input}" is not a valid choice.')
    }

    def __init__(self, queryset=None, **kwargs):
        self.queryset = queryset
        self.allow_blank = kwargs.pop('allow_blank', False)
        super().__init__(**kwargs)

    @property
    def choice_string_to_values(self):
        grouped_choices = serializers.to_choices_dict(
            self.queryset() if callable(self.queryset) else self.queryset)
        choices = serializers.flatten_choices_dict(grouped_choices)
        return {
            six.text_type(key): key for key in choices.keys()
        }

    def to_internal_value(self, data):
        if data == '' and self.allow_blank:
            return ''

        if not self.queryset:
            return data

        try:
            return self.choice_strings_to_values[six.text_type(data)]
        except KeyError:
            self.fail('invalid_choice', input=data)

    def to_representation(self, value):
        if value in ('', None):
            return value
        if not self.queryset:
            return value
        return self.choice_strings_to_values.get(six.text_type(value), value)


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
        return dictionary[self.field_name]


class Serializer(geojson.Serializer):
    def get_dump_object(self, obj):
        property_map = self.options.get('properties', None)
        for name, new_name in property_map.items():
            if name in self._current:
                self._current[new_name] = self._current[name]
                del self._current[name]
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