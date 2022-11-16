from unittest.mock import MagicMock

import pytest

from django.contrib.auth.models import Permission
from django.urls import reverse

from accounts.models import PermissionSet
from activity.models import Event, EventCategory
from activity.permissions import EventCategoryGeographicPermission
from activity.views import EventsView, EventView
from client_http import HTTPClient
from utils.gis import convert_to_point


@pytest.mark.django_db
class TestEventGeoJsonPermissions:
    @pytest.mark.parametrize(
        "known_location",
        [
            {
                "location": "-103.527837, 20.668671",
                "known_distance_meters": 1200,
                "result": False,
                "category": "analyzer_event",
            },
            {
                "location": "-103.523242, 20.655429",
                "known_distance_meters": 2000,
                "result": False,
                "category": "logistics",
            },
            {
                "location": "-103.520739, 20.669644",
                "known_distance_meters": 500,
                "result": True,
                "category": "monitoring",
            },
            {
                "location": "-103.519298, 20.671825",
                "known_distance_meters": 250,
                "result": True,
                "category": "security",
            },
        ],
    )
    def test_geo_json_location_permission(self, five_events, known_location, settings, rf, monkeypatch):
        mock = MagicMock(return_value=False)
        monkeypatch.setattr("activity.permissions.is_banned", mock)

        url = f"{reverse('events')}?location=-103.517015, 20.672398"
        request = rf.get(url)
        client = HTTPClient()

        permission_name = f"view_{known_location['category']}_geographic_distance"
        geojson_set = PermissionSet.objects.create(name="geojson_set")
        geojson_set.permissions.add(Permission.objects.get(codename=permission_name))
        client.app_user.permission_sets.add(geojson_set)
        request.user = client.app_user

        event = Event.objects.order_by("created_at").last()
        category = EventCategory.objects.get_or_create(value=known_location["category"])[0]
        event.event_type.category = category
        event.event_type.save()
        event.location = convert_to_point(known_location["location"])
        event.save()

        settings.GEO_PERMISSION_RADIUS_METERS = 1000
        permission = EventCategoryGeographicPermission()
        has_object_permission = permission.has_object_permission(request, None, event)

        assert has_object_permission == known_location["result"]
        assert client.app_user.has_perm(f"activity.{permission_name}") is True
        assert "location" in request.GET


@pytest.mark.django_db
class TestEventGeometryPermissions:
    def _get_permission_set(self, event: Event):
        category = event.event_type.category

        perm_set = PermissionSet.objects.filter(
            permissions__codename__icontains=f"{category.value}_geographic_distance"
        ).first()
        return perm_set

    @pytest.mark.parametrize(
        "location,expected",
        [
            ["-114.82910156249999,33.17434155100208", 1],
            ["0,0", 0],
        ],
    )
    def test_list_events_with_geometries_and_geo_permissions(self, event_geometry_with_polygon, location, expected):
        perm_set = self._get_permission_set(event_geometry_with_polygon.event)

        url = f"{reverse('events')}?location={location}"

        client = HTTPClient()
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)
        client.app_user.permission_sets.add(perm_set)
        response = EventsView.as_view()(request)

        assert response.data["count"] == expected
        if expected:
            assert response.data["results"][0]["id"] == str(event_geometry_with_polygon.event.id)

    @pytest.mark.parametrize("location,expected", [["1,1", 201], ["0.98888933029999,1", 403]])
    def test_create_event_geometry_with_permission_limit_radius(self, event_geometry_with_polygon, location, expected):
        perm_set = self._get_permission_set(event_geometry_with_polygon.event)
        url = f"{reverse('events')}?location={location}"

        data = {
            "event_type": event_geometry_with_polygon.event.event_type.value,
            "title": "Test Polygon",
            "event_category": "second_polygon",
            "geometry": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [1.0250866712506195, 0.9984320718818367],
                                    [1.0425130492343726, 0.9952809698736189],
                                    [1.037878374238744, 1.009738942395117],
                                    [1.0250866712506195, 0.9984320718818367],
                                ]
                            ],
                        },
                    }
                ],
            },
        }

        client = HTTPClient()
        request = client.factory.post(url, data=data)
        client.force_authenticate(request, client.app_user)
        client.app_user.permission_sets.add(perm_set)

        response = EventsView.as_view()(request)

        assert response.status_code == expected

    @pytest.mark.parametrize(
        "location,data,expected_status_code",
        [
            ["-114.85910156249999,33.17434155100208", {"title": "New title 1"}, 200],
            ["-114.89910156249999,33.17434155100208", {"title": "New title 2"}, 403],
        ],
    )
    def test_update_event_with_geometry_and_geo_permissions(
        self, event_geometry_with_polygon, location, data, expected_status_code
    ):
        perm_set = self._get_permission_set(event_geometry_with_polygon.event)

        event_id = event_geometry_with_polygon.event.id
        url = f"{reverse('event-view', kwargs= {'id': event_id})}/?location={location}"

        client = HTTPClient()
        request = client.factory.patch(url, data)
        client.force_authenticate(request, client.app_user)
        client.app_user.permission_sets.add(perm_set)

        response = EventView.as_view()(request, id=event_id)

        assert response.status_code == expected_status_code

    @pytest.mark.parametrize(
        "location,expected_status_code",
        [
            ["-114.85910156249999,33.17434155100208", 204],
            ["-114.89910156249999,33.17434155100208", 403],
        ],
    )
    def test_delete_event_with_geometry_and_geo_permissions(
        self, event_geometry_with_polygon, location, expected_status_code
    ):
        perm_set = self._get_permission_set(event_geometry_with_polygon.event)

        event_id = event_geometry_with_polygon.event.id
        url = f"{reverse('event-view', kwargs={'id': event_id})}/?location={location}"
        client = HTTPClient()
        request = client.factory.delete(url)
        client.force_authenticate(request, client.app_user)
        client.app_user.permission_sets.add(perm_set)

        response = EventView.as_view()(request, id=event_id)

        assert response.status_code == expected_status_code
