from drf_extra_fields.geo_fields import PointField
from django.contrib.gis.geos import GEOSGeometry
from rest_framework import serializers
from rest_framework.fields import empty


def choicefield_serializer(choices, default=empty, **kwargs):
    return serializers.ChoiceField(choices=choices, default=default, **kwargs)


def text_field(**kwargs):
    style = kwargs.pop('style', {'base_template': 'textarea.html'})
    return serializers.CharField(style=style, **kwargs)


class GEOPointField(PointField):

    def to_representation(self, value):
        """
        Transform POINT object to json.
        """
        if value is None:
            return value

        if isinstance(value, GEOSGeometry):
            value = {
                "latitude": value.y,
                "longitude": value.x
            }
        return value