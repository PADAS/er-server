import json
import logging

import geojson
import jsonschema
from dateutil.parser import parse as parse_date
from drf_extra_fields.fields import DateTimeTZRange, RangeField
from geojson import Feature, FeatureCollection

from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.fields import DateTimeField
from rest_framework.utils import html

from activity.models import EventGeometry
from utils.feature_representation import FeatureFactory

logger = logging.getLogger(__name__)


class CoordinateField(serializers.Field):
    allow_null = True
    schema = {
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number"
            },
            "longitude": {
                "type": "number"
            }
        }
    }

    @classmethod
    def validate(cls, data):
        try:
            jsonschema.validate(instance=data, schema=cls.schema)
        except jsonschema.exceptions.ValidationError as ex:
            raise serializers.ValidationError(ex.message)

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        self.validate(data)

        return data


class _RangeField(RangeField):

    def to_internal_value(self, data):
        if html.is_html_input(data):
            data = html.parse_html_dict(data)
        if not isinstance(data, dict):
            self.fail('not_a_dict', input_type=type(data).__name__)
        lower, upper = data.get('start_time'), data.get('end_time')
        self.validate_time_range(lower, upper)
        data = {'lower': lower, 'upper': upper}
        return super().to_internal_value(data)

    def validate_time_range(self, lower, upper):
        if lower and upper and parse_date(lower) > parse_date(upper):
            raise ValidationError(
                'start_time must be an earlier date than the end_time')

    def to_representation(self, value):
        """
        Range instances -> dicts of primitive datatypes.
        """
        if value.isempty:
            return {'empty': True}
        lower = self.child.to_representation(
            value.lower) if value.lower is not None else None
        upper = self.child.to_representation(
            value.upper) if value.upper is not None else None
        return {'start_time': lower,
                'end_time': upper
                }


class DateTimeRangeField(_RangeField):
    child = DateTimeField(allow_null=True)
    range_type = DateTimeTZRange


class EventGeometryField(serializers.RelatedField):
    def __init__(self, **kwargs):
        self._feature_factory = FeatureFactory()
        super().__init__(**kwargs)

    def get_queryset(self):
        queryset = EventGeometry.objects.all()
        return queryset

    def to_representation(self, value):
        events_geometries = value.all()
        if events_geometries:
            return FeatureCollection(
                [
                    self._feature_factory.get_for_feature(
                        self._get_geometry_type(event_geometry.geometry)
                    ).get(
                        self._get_geometry_coordinates(
                            event_geometry.geometry),
                        event_geometry.properties,
                    )
                    for event_geometry in events_geometries
                ]
            )
        return None

    def to_internal_value(self, data):
        try:
            feature = geojson.loads(geojson.dumps(data))
            if not isinstance(feature, FeatureCollection) and not isinstance(
                feature, Feature
            ):
                raise ValidationError(
                    {
                        "geometry": "Error in format of geometry field, it should be a Feature or a FeatureCollection."
                    }
                )
        except Exception as e:
            raise ValidationError(
                {"geometry": f"Error parsing geometry field {e}"})
        return data

    def _get_geometry_type(self, geometry):
        try:
            geometry_json = json.loads(geometry.json)
            return geometry_json.get("type")
        except TypeError:
            logger.exception(
                f"Trying to parse a wrong type of geometry {geometry}.")

    def _get_geometry_coordinates(self, geometry):
        try:
            return geometry.coords
        except AttributeError:
            logger.exception(
                f"Was tried to get an attribute that does not exist.")
