import logging
from abc import ABC, abstractmethod
from typing import Union

from geojson import Feature, Polygon
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from rest_framework.request import Request

from activity.models import Event, EventGeometry
from utils import add_base_url

logger = logging.getLogger(__name__)


class EventSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Event
        geo_field = "location"
        fields = ["location"]


class EventGeometrySerializer(GeoFeatureModelSerializer):
    class Meta:
        model = EventGeometry
        geo_field = "geometry"
        fields = ["geometry"]


class FeatureRepresentation:
    """ A class for figure representation such as Point, Polygon as GeoJSON. """
    serializers = {"Event": EventSerializer,
                   "EventGeometry": EventGeometrySerializer}

    def get_feature(self, request: Request, instance: Union[Event, EventGeometry]):
        try:
            model_name = instance._meta.object_name
            feature = self.serializers[model_name](instance).data
            if model_name == "Event":
                image_url = self._get_image_url(request, instance)
                feature["properties"] = self._get_properties(
                    instance, image_url)
                if image_url:
                    feature["properties"]["icon"] = self._get_icon(image_url)
            elif model_name == "EventGeometry":
                feature["properties"] = instance.properties
            return feature
        except Exception as e:
            logger.exception("TODO Error creating feature  %s", e)

    def _get_properties(self, event: Event, imagen_url: str):
        return {
            "message": event.message,
            "datetime": event.time
            if isinstance(event.time, str)
            else event.time.isoformat(),
            "image": imagen_url,
        }

    def _get_image_url(self, request: Request, event: Event):
        image_url = event.image_url
        return add_base_url(request, image_url)

    def _get_icon(self, image_url: str):
        return {
            "iconUrl": image_url,
            "iconSize": [25, 25],
            "iconAncor": [12, 12],
            "popupAncor": [0, -13],
            "className": "dot",
        }


class GeometryFeature(ABC):
    @abstractmethod
    def get(self, coordinates: dict, properties: dict) -> Feature:
        pass


class PolygonFeature(GeometryFeature):
    def get(self, coordinates: tuple, properties: dict) -> Feature:
        return Feature(geometry=Polygon(coordinates), properties=properties)


class FeatureFactory:
    _features = {
        "Polygon": PolygonFeature()
    }

    def get_for_feature(self, sort):
        try:
            return self._features[sort]
        except KeyError:
            raise ValueError(f"Type {sort} not supported for FeatureFactory")
