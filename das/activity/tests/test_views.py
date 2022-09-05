import pytest

from django.contrib.gis.geos import Polygon
from django.urls import reverse
from rest_framework import status

from activity.models import Event, EventGeometry
from utils.features import features


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

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    def test_create_an_event_with_a_feature_collection_as_geometry(
        self, event_type, superuser_client
    ):
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

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    def test_create_an_event_with_a_feature_as_geometry(
        self, event_type, superuser_client
    ):
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

    @pytest.mark.parametrize("geometry", (feature, feature_collection))
    def test_updated_geometry_of_event_that_contains_a_previous_geometry(
        self, geometry, event_with_detail, superuser_client
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

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.skipif(features.geometries.is_on() is False, reason="Geometries feature flag is off")
    @pytest.mark.parametrize("geometry", (feature, feature_collection))
    def test_update_geometry_of_event_that_does_not_contains_a_geometry(self, geometry, event_with_detail, superuser_client):

        url = reverse("event-view", args=[event_with_detail.event.pk])
        response = superuser_client.patch(url, {"geometry": geometry})

        assert response.status_code == status.HTTP_200_OK
        assert EventGeometry.objects.all().count()
