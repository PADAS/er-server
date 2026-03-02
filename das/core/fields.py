import uuid

from django_multitenant.fields import TenantForeignKey
from drf_extra_fields.geo_fields import PointField

from django.contrib.gis.geos import GEOSGeometry
from rest_framework import serializers
from rest_framework.fields import empty


class StrictUUIDField(serializers.UUIDField):
    allowed_versions = {1, 2, 3, 4, 5}  # add 7 when you're ready

    def to_internal_value(self, data):
        u = super().to_internal_value(data)  # uses uuid.UUID parsing
        if u.variant != uuid.RFC_4122:
            raise serializers.ValidationError("UUID must be RFC 4122 variant.")
        if u.version not in self.allowed_versions:
            raise serializers.ValidationError(f"Unsupported UUID version: {u.version}.")
        return u


class CompoundTenantForeignKey(TenantForeignKey):
    pass


class AlternateSpellingChoiceField(serializers.ChoiceField):
    def __init__(self, *args, **kwargs):
        self.alternate_spellings = kwargs.pop("alternate_spellings", {})
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if str(data) in self.alternate_spellings:
            data = self.alternate_spellings[str(data)]
        return super().to_internal_value(data)


def choicefield_serializer(choices, default=empty, **kwargs):
    if "alternate_spellings" in kwargs:
        return AlternateSpellingChoiceField(choices=choices, default=default, **kwargs)
    return serializers.ChoiceField(choices=choices, default=default, **kwargs)


def text_field(**kwargs):
    style = kwargs.pop("style", {"base_template": "textarea.html"})
    return serializers.CharField(style=style, **kwargs)


class GEOPointField(PointField):
    def to_representation(self, value):
        """
        Transform POINT object to json.
        """
        if value is None:
            return value

        if isinstance(value, GEOSGeometry):
            value = {"latitude": value.y, "longitude": value.x}
        return value
