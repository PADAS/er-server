from unittest.mock import MagicMock

import pytest

from django.contrib.auth.models import Permission
from django.urls import reverse

from accounts.models import PermissionSet
from activity.models import Event, EventCategory
from activity.permissions import EventCategoryGeographicPermission
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
    def test_geo_json_location_permission(
            self, five_events, known_location, settings, rf, monkeypatch
    ):
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
        category = EventCategory.objects.get_or_create(
            value=known_location["category"]
        )[0]
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
