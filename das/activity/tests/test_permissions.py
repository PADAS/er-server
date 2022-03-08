import pytest
from accounts.models import PermissionSet
from activity.models import Event, EventCategory
from activity.permissions import EventCategoryGeographicPermission
from client_http import HTTPClient
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse


@pytest.mark.django_db
class TestEventGeoJsonPermissions:
    @pytest.mark.parametrize("known_location",
                             [{"location": "20.668671, -103.527837", "known_distance_meters": 1200, "result": False,
                               "category": "analyzer_event"},
                              {"location": "20.655429, -103.523242", "known_distance_meters": 2000, "result": False,
                               "category": "logistics"},
                              {"location": "20.669644, -103.520739", "known_distance_meters": 500, "result": True,
                               "category": "monitoring"},
                              {"location": "20.671825, -103.519298", "known_distance_meters": 250, "result": True,
                               "category": "security"}, ], )
    def test_geo_json_location_permission(self, five_events, known_location, settings, rf):
        request = rf.get(reverse("events"))
        client = HTTPClient()

        permission_name = f"view_{known_location['category']}_geographic_distance"
        geojson_set = PermissionSet.objects.create(name="geojson_set")
        geojson_set.permissions.add(
            Permission.objects.get(codename=permission_name))
        client.app_user.permission_sets.add(geojson_set)
        request.user = client.app_user

        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session["location"] = "20.672398, -103.517015"
        request.session.save()

        event = Event.objects.order_by("created_at").last()
        category = EventCategory.objects.get_or_create(
            value=known_location["category"]
        )[0]
        event.event_type.category = category
        event.event_type.save()
        latitude = float(known_location["location"].split(",")[0].strip())
        longitude = float(known_location["location"].split(",")[1].strip())
        event.location = Point(longitude, latitude, srid=4326)
        event.save()

        settings.GEO_PERMISSION_ENABLED = True
        settings.GEO_PERMISSION_RADIUS_METERS = 1000
        permission = EventCategoryGeographicPermission()
        has_object_permission = permission.has_object_permission(
            request, None, event)
        assert has_object_permission == known_location["result"]
        assert client.app_user.has_perm(f"activity.{permission_name}") is True
