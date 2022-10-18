import json

import pytest

from django.contrib.gis.geos import Point, Polygon

from activity.models import EventGeometry
from activity.serializers import EventGeometryField


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestEventGeometryField:
    def test_serialized_geometry_format(self, event_with_detail):
        event = event_with_detail.event
        EventGeometry.objects.create(
            event=event,
            geometry=Polygon(
                (
                    (-103.41898441314697, 20.638567565077864),
                    (-103.41387748718262, 20.63499318125139),
                    (-103.40585231781006, 20.646840535793658),
                    (-103.41898441314697, 20.638567565077864),
                )
            ),
            properties={"size": "L", "color": "Green", "width": 15},
        )

        serialized_geometry = EventGeometryField().to_representation(event.geometries)
        features = serialized_geometry.get("features")
        feature = features[0]
        geometry = feature.get("geometry")
        coordinates = geometry.get("coordinates")
        geometry_type = geometry.get("type")
        properties = feature.get("properties")
        keys = {"type", "geometry", "properties"}

        assert isinstance(serialized_geometry, dict)
        assert isinstance(serialized_geometry.get("type"), str)
        assert isinstance(features, list)
        assert isinstance(feature, dict)
        assert keys == set(features[0].keys())
        assert isinstance(feature.get("type"), str)
        assert isinstance(feature.get("geometry"), dict)
        assert isinstance(feature.get("properties"), dict)
        assert isinstance(properties, dict)
        assert isinstance(geometry, dict)
        assert isinstance(geometry_type, str)
        assert isinstance(coordinates, list)
        assert isinstance(coordinates[0], list)
        assert isinstance(coordinates[0][0], list)

    def test_serialized_geometry(self, event_with_detail):
        event = event_with_detail.event
        event_geometry = EventGeometry.objects.create(
            event=event,
            geometry=Polygon(
                (
                    (-103.418984, 20.638567),
                    (-103.413877, 20.634993),
                    (-103.405852, 20.646840),
                    (-103.418984, 20.638567),
                )
            ),
            properties={"size": "L", "color": "Green", "width": 15},
        )

        serialized_geometry = EventGeometryField().to_representation(event.geometries)
        feature = serialized_geometry.get("features")[0]

        expected_geometry = feature.get("geometry")
        if "is_valid" in expected_geometry:
            del expected_geometry["is_valid"]

        assert serialized_geometry.get("type") == "FeatureCollection"
        assert feature.get("type") == "Feature"
        assert feature.get("properties") == event_geometry.properties
        assert feature.get("geometry") == json.loads(event_geometry.geometry.geojson)

    def test_serialized_point_geometry(self, event_with_detail):
        event = event_with_detail.event
        event_geometry = EventGeometry.objects.create(
            event=event,
            geometry=Point(-103.418984, 20.638567),
            properties={"size": "S", "color": "Red", "width": 5},
        )

        serialized_geometry = EventGeometryField().to_representation(event.geometries)
        feature = serialized_geometry.get("features")[0]

        expected_geometry = feature.get("geometry")
        if "is_valid" in expected_geometry:
            del expected_geometry["is_valid"]

        assert serialized_geometry.get("type") == "FeatureCollection"
        assert feature.get("type") == "Feature"
        assert feature.get("properties") == event_geometry.properties
        assert feature.get("geometry") == json.loads(event_geometry.geometry.geojson)
        assert feature.get("geometry").get("type") == "Point"
        assert feature.get("geometry").get("coordinates") == [-103.418984, 20.638567]

    def test_serialized_empty_geometry(self, event_with_detail):
        serialized_geometry = EventGeometryField().to_representation(event_with_detail.event.geometries)

        assert serialized_geometry is None
