from abc import ABC, abstractmethod

from django.contrib.gis.geos import Polygon

from activity.models import Event, EventGeometry
from utils.gis import get_polygon_info


class EventGeometryCreator(ABC):
    @abstractmethod
    def create(self, event: Event, coordinates: list, properties: dict) -> EventGeometry:
        pass


class PolygonEventGeometry(EventGeometryCreator):
    def create(self, event: Event, coordinates: list, properties: dict) -> EventGeometry:
        instance = EventGeometry(
            event=event, geometry=Polygon(coordinates), properties=properties
        )
        instance.properties["area"] = get_polygon_info(
            instance.geometry, "area")
        instance.properties["perimeter"] = get_polygon_info(
            instance.geometry, "length")
        return instance.save()


class EventGeometryFactory(ABC):
    @abstractmethod
    def create_event_geometry(self, geometry_type: str) -> EventGeometryCreator:
        pass


class GenericGeometryFactory(EventGeometryFactory):
    _geometries = {
        "Polygon": PolygonEventGeometry()
    }

    def create_event_geometry(self, geometry_type: str) -> EventGeometryCreator:
        try:
            return self._geometries[geometry_type]
        except KeyError:
            raise ValueError(
                f"Type {geometry_type} not supported for event GeometryFactory.")
