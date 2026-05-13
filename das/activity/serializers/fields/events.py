import json
import logging
from collections import OrderedDict

import geojson
import jsonschema
from geojson import Feature, FeatureCollection

from rest_framework.serializers import JSONField, RelatedField, ValidationError

from activity.models import (
    EventCategory,
    EventGeometry,
    EventRelationshipType,
    EventSource,
    EventType,
)
from activity.serializers.helpers import resolve_external_event_source
from utils.feature_representation import FeatureFactory

logger = logging.getLogger(__name__)


class EventRelationshipTypeRelatedField(RelatedField):
    def get_queryset(self):
        return EventRelationshipType.objects.all_sort()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            return EventRelationshipType.objects.get_by_value(data)
        return None

    @property
    def choices(self):
        return OrderedDict(((row.value, row.value) for row in self.get_queryset()))


class EventGeometryField(RelatedField):
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
                    self._feature_factory.get_for_feature(self._get_geometry_type(event_geometry.geometry)).get(
                        self._get_geometry_coordinates(event_geometry.geometry),
                        event_geometry.properties,
                    )
                    for event_geometry in events_geometries
                ]
            )
        return None

    def to_internal_value(self, data):
        try:
            feature = geojson.loads(geojson.dumps(data))
            if not isinstance(feature, FeatureCollection) and not isinstance(feature, Feature):
                raise ValidationError(
                    {"geometry": "Error in format of geometry field, it should be a Feature or a FeatureCollection."}
                )
        except Exception as error:
            raise ValidationError({"geometry": f"Error parsing geometry field {error}"})
        return data

    def _get_geometry_type(self, geometry):
        try:
            geometry_json = json.loads(geometry.json)
            return geometry_json.get("type")
        except TypeError:
            logger.exception(f"Trying to parse a wrong type of geometry {geometry}.")
            return None

    def _get_geometry_coordinates(self, geometry):
        try:
            coords = geometry.coords
            if coords is None:
                logger.exception("Geometry coordinates are None.")
                return None
            return coords
        except AttributeError:
            logger.exception("Was tried to get an attribute that does not exist.")
            return None


class EventAttributesField(JSONField):
    def __init__(self, event_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schema = None
        if event_type:
            self.schema = event_type.schema

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if not self.schema and data:
            raise ValidationError("Schema not set for Event.Attributes")
        if self.schema is None:
            return data
        try:
            jsonschema.validate(data, self.schema)
        except jsonschema.ValidationError as error:
            raise ValidationError(error.message)

        return data


class EventSourceRelatedField(RelatedField):
    def get_queryset(self):
        user = self.context["request"].user
        if not getattr(user, "is_authenticated", False):
            return EventSource.objects.none()
        return EventSource.objects.filter(eventprovider__owner=user)

    def to_representation(self, value):
        return value.id if value else None

    def to_internal_value(self, data):
        if data:
            try:
                user = self.context["request"].user
            except AttributeError:
                pass
            else:
                try:
                    return EventSource.objects.get(id=data, eventprovider__owner=user)
                except EventSource.DoesNotExist:  # type: ignore
                    raise ValidationError({"eventsource": f"ID '{data}' does not exist."})
        return None

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display) for row in self.get_queryset()))


class EventTypeRelatedField(RelatedField):
    def get_queryset(self):
        queryset = EventType.objects.all_sort()
        view = self.context.get("view")
        if view and view.get_view_name() == "Event Schema":
            event_categories = EventCategory.get_category_keys()
            actions = ("create", "update", "read", "delete")
            allowed_event_categories = []
            for event_category in event_categories:
                permission_name = [f"activity.{event_category}_{action}" for action in actions]
                request = self.context.get("request")
                if request and request.user and any([request.user.has_perm(perm) for perm in permission_name]):
                    allowed_event_categories.append(event_category)

            return queryset.by_category(allowed_event_categories) if allowed_event_categories else queryset.none()
        else:
            return queryset

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            try:
                return EventType.objects.get_by_value(data)
            except EventType.DoesNotExist:  # type: ignore
                raise ValidationError({"event_type": f"Value '{data}' does not exist."})
        else:
            request_data = self.context["request"].data
            external_event_type = request_data.get("external_event_type")
            if external_event_type:
                request = self.context.get("request")
                if request and request.user:
                    eventsource = resolve_external_event_source(request.user, external_event_type)
                    if eventsource:
                        return eventsource.event_type

        return None

    @property
    def choices(self):
        queryset = self.get_queryset()
        if queryset is None:
            return OrderedDict()
        return OrderedDict(((row.value, row.display) for row in queryset))
