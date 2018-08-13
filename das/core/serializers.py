import rest_framework.serializers as serializers
from django.contrib.contenttypes.models import ContentType
import django.contrib.gis.serializers.geojson as geojson


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
