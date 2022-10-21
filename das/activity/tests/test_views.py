import pytest

from django.contrib.gis.geos import Polygon
from django.urls import reverse
from rest_framework import status

from activity.models import Event, EventGeometry, EventType
from utils.gis import get_polygon_info


@pytest.mark.django_db
class TestEventsView:
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-121.77246093750001, 47.96050238891509],
                    [-118.037109375, 32.879587173066305],
                    [-83.75976562499999, 30.826780904779774],
                    [-84.5947265625, 45.1510532655634],
                    [-95.5810546875, 48.719961222646276],
                    [-121.77246093750001, 47.96050238891509],
                ]
            ],
        },
    }
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-103.64158630371094, 20.67037186452816],
                            [-103.64398956298828, 20.652382371230658],
                            [-103.63197326660155, 20.653667405666592],
                            [-103.64158630371094, 20.67037186452816],
                        ]
                    ],
                },
            }
        ],
    }

    # Area = 18876, Perimeter = 551
    feature_with_known_dimensions = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-103.3813151344657, 20.67669767171168],
                    [-103.38131647557019, 20.67563084151954],
                    [-103.3799860998988, 20.675623940505954],
                    [-103.37997503578663, 20.676691711787292],
                    [-103.3813151344657, 20.67669767171168],
                ]
            ],
        },
    }

    def test_create_an_event_with_a_feature_collection_as_geometry(
        self, event_type, superuser_client
    ):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
        url = reverse("events")

        response = superuser_client.post(
            url,
            {
                "title": "Event number five",
                "event_type": event_type.value,
                "geometry": self.feature_collection,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Event.objects.all().count()
        assert EventGeometry.objects.all().count() == 1

    def test_create_an_event_with_a_feature_as_geometry(
        self, event_type, superuser_client
    ):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
        url = reverse("events")

        response = superuser_client.post(
            url,
            {
                "title": "Event number five",
                "event_type": event_type.value,
                "geometry": self.feature,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Event.objects.all().count()
        assert EventGeometry.objects.all().count()
        assert "area" in response.data["geometry"]["features"][0]["properties"]

    def test_calculate_geometry_area_and_perimeter(self, event_type, superuser_client):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
        url = reverse("events")

        response = superuser_client.post(
            url,
            {
                "title": "Event number five",
                "event_type": event_type.value,
                "geometry": self.feature_with_known_dimensions,
            },
        )
        area = response.data['geometry'][0]['properties']["area"]
        perimeter = response.data['geometry'][0]['properties']["perimeter"]

        assert response.status_code == status.HTTP_201_CREATED
        assert int(area) == 16438
        assert int(perimeter) == 514


@pytest.mark.django_db
class TestEventView:
    feature = {
        "type": "Feature",
        "properties": {"title": "This is a new title", "size": 10, "large": 20},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-130.166015625, 66.93006025862448],
                    [-125.771484375, 51.34433866059924],
                    [-85.869140625, 49.83798245308484],
                    [-92.10937499999999, 66.5482634621744],
                    [-130.166015625, 66.93006025862448],
                ]
            ],
        },
    }
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "color": "green"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-103.64158630371094, 20.67037186452816],
                            [-103.64398956298828, 20.652382371230658],
                            [-103.63197326660155, 20.653667405666592],
                            [-103.64158630371094, 20.67037186452816],
                        ]
                    ],
                },
            }
        ],
    }

    @pytest.mark.parametrize(
        "geometry, expected",
        (
            (feature, {"area": 3846072269393, "perimeter": 8185448}),
            (feature_collection, {"area": 1228789, "perimeter": 5370}),
        ),
    )
    def test_updated_geometry_of_event_that_contains_a_previous_geometry(
        self, geometry, expected, event_with_detail, superuser_client
    ):
        EventGeometry.objects.create(
            event=event_with_detail.event,
            geometry=Polygon(
                (
                    (-103.41898441314697, 20.638567565077864),
                    (-103.41387748718262, 20.63499318125139),
                    (-103.40585231781006, 20.646840535793658),
                    (-103.41898441314697, 20.638567565077864),
                )
            ),
            properties={
                "title": "This is a little title"
            }
        )

        url = reverse("event-view", args=[event_with_detail.event.pk])
        response = superuser_client.patch(url, {"geometry": geometry})

        area = response.data['geometry'][0]['properties']["area"]
        perimeter = response.data['geometry'][0]['properties']["perimeter"]

        assert response.status_code == status.HTTP_200_OK
        assert int(area) == expected["area"]
        assert int(perimeter) == expected["perimeter"]

    @pytest.mark.parametrize(
        "geometry, expected",
        (
            (feature, {"area": 3846072269393, "perimeter": 8185448}),
            (feature_collection, {"area": 1228789, "perimeter": 5370}),
        ),
    )
    def test_update_geometry_of_event_that_does_not_contains_a_geometry(self, geometry, expected, event_with_detail, superuser_client):
        url = reverse("event-view", args=[event_with_detail.event.pk])
        response = superuser_client.patch(url, {"geometry": geometry})

        area = response.data['geometry'][0]['properties']["area"]
        perimeter = response.data['geometry'][0]['properties']["perimeter"]

        assert response.status_code == status.HTTP_200_OK
        assert int(area) == expected["area"]
        assert int(perimeter) == expected["perimeter"]
        assert EventGeometry.objects.all().count()

    def test_delete_event_geometry_of_event(self, event_geometry_with_polygon, superuser_client):
        url = reverse(
            "event-view", args=[event_geometry_with_polygon.event.pk])

        response = superuser_client.patch(url, {"geometry": None})

        assert response.status_code == status.HTTP_200_OK
        assert event_geometry_with_polygon.event.geometries.count() == 0

    def test_delete_event_geometry_of_event_without_geometry(self, event_with_detail, superuser_client):
        url = reverse("event-view", args=[event_with_detail.event.pk])

        response = superuser_client.patch(url, {"geometry": None})

        assert response.status_code == status.HTTP_200_OK
        assert event_with_detail.event.geometries.count() == 0


@pytest.mark.django_db
class TestEventGeometryView:

    def test_get_event_geometry_updates(self, event_geometry_with_polygon,  superuser_client):
        event = event_geometry_with_polygon.event

        url = reverse("event-geometries", args=[event.id])
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_get_event_geometry_updates_properties(self, event_geometry_with_polygon,  superuser_client):
        event_geometry_with_polygon.properties = {"key": "value"}
        event_geometry_with_polygon.save()
        event = event_geometry_with_polygon.event

        url = reverse("event-geometries", args=[event.id])
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_get_event_geometry_update_without_revisions(self, event_with_detail, superuser_client):

        url = reverse("event-geometries", args=[event_with_detail.event.id])
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert not response.data

    def test_export_events_csv(self, event_geometry_with_polygon, superuser_client):
        url = reverse("events-export")
        event_geometry_with_polygon.properties["area"] = get_polygon_info(
            event_geometry_with_polygon.geometry, "area"
        )
        event_geometry_with_polygon.properties["perimeter"] = get_polygon_info(
            event_geometry_with_polygon.geometry, "length"
        )
        event_geometry_with_polygon.save()
        response = superuser_client.get(url)
        content = response.content.decode("utf-8")

        assert response.status_code == status.HTTP_200_OK
        assert "Area" in content
        assert "3215419796603.78" in content
        assert "Perimeter" in content
        assert "8791536.63" in content
