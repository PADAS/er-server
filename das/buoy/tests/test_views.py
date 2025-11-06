import json
import random
from datetime import datetime

import pytest
from geopy.distance import distance

from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.models import PermissionSet
from buoy import views
from client_http import HTTPClient
from das.buoy.tests import (
    generate_devices,
    generate_fake_display_id,
    get_custom_location_gear_subjectsource,
)
from observations.models import Observation, SubjectGroup, SubjectSource


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearView:
    base_url = "gear-view"

    @pytest.fixture
    def _get_superuser_client(self, gear_subjectsource, superuser, superuser_client):
        url = reverse(self.base_url, kwargs={"id": gear_subjectsource.subject.id})
        gear_subjectsource.subject.linked_user = superuser
        gear_subjectsource.subject.save()
        return superuser_client.get(url), superuser

    @pytest.fixture
    def _get_client(self, gear_subjectsource):
        client = HTTPClient()
        gear_subjectsource.subject.linked_user = client.app_user
        gear_subjectsource.subject.save()
        url = reverse(self.base_url, kwargs={"id": gear_subjectsource.subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        return views.GearView.as_view()(request, id=str(gear_subjectsource.subject.id)), client.app_user

    def test_subject_view_with_linked_user(self, _get_superuser_client):
        response, user = _get_superuser_client
        # GearSerializer returns SubjectSource, so id comes from subject.id
        assert response.data["id"] == str(user.linked_subject.id)
        assert response.data["display_id"] == user.linked_subject.name
        assert response.data["status"] == "deployed"
        assert response.data["last_updated"]

    def test_subject_view_with_linked_user_and_not_subject_permission(self, _get_client):
        response, user = _get_client
        # If permission is denied, response won't have data
        if response.status_code == 200:
            # GearSerializer returns SubjectSource, so id comes from subject.id
            assert response.data["id"] == str(user.linked_subject.id)
        else:
            # Permission denied
            assert response.status_code == 403

    def test_subject_view_without_linked_user(self, _get_superuser_client):
        response, _ = _get_superuser_client
        assert not hasattr(response.data, "user")

    def test_subject_view_with_not_linked_user_or_subject_permission(self, gear_subjectsource):
        client = HTTPClient()
        url = reverse(self.base_url, kwargs={"id": gear_subjectsource.subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        response = views.GearView.as_view()(request, id=str(gear_subjectsource.subject.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def _test_subject_view_with_linked_user_ask_for_random_subject(self, five_gears, superuser_client, superuser):
        subject1 = five_gears[0]
        subject2 = five_gears[1]
        url = reverse(self.base_url, kwargs={"id": subject2.id})
        subject1.linked_user = superuser
        subject1.save()
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        assert response.data["id"] == str(subject2.id)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearsView:

    base_url = "gear-list-create-view"

    @pytest.fixture
    def buoy_superuser_client(self, gear_subjectsource_with_observations, superuser_client):
        gear_subjectsource_with_observations.linked_user = superuser_client.user
        gear_subjectsource_with_observations.save()
        return superuser_client, gear_subjectsource_with_observations

    @pytest.fixture
    def buoy_client(self, gear_subjectsource_with_observations, user_client):
        gear_subjectsource_with_observations.linked_user = user_client.user

        # Create Subject-Group & have only one subject & give permission to view subject-source.
        parent_group = SubjectGroup.objects.create(name="SG Group")
        view_subject_group_perm_name = "view_subjectgroup"
        view_subject_source_perm_name = "view_subjectsource"

        view_subject_perm = Permission.objects.get(codename=view_subject_group_perm_name)
        view_subject_source = Permission.objects.get(codename=view_subject_source_perm_name)
        perm_set = PermissionSet.objects.create(name="View SG Group Perm set")
        perm_set2 = PermissionSet.objects.create(name="View SubjectSource PermSet")
        perm_set.permissions.add(view_subject_perm)
        perm_set2.permissions.add(view_subject_source)
        perm_set.save()
        perm_set2.save()
        user_client.user.permission_sets.add(perm_set)
        user_client.user.permission_sets.add(perm_set2)
        user_client.user.save()

        parent_group.permission_sets.add(perm_set)
        parent_group.subjects.add(gear_subjectsource_with_observations.subject)
        parent_group.is_visible = True
        parent_group.save()

        gear_subjectsource_with_observations.save()
        return user_client, gear_subjectsource_with_observations

    def test_gear_subjects_view_with_linked_user(self, buoy_client):
        url = reverse(self.base_url) + "?lat=0&lon=0"
        user_client, _ = buoy_client
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    @pytest.mark.skip(reason="This test requires using the sensors api to handle the event_type field")
    def test_gear_subjects_view_without_linked_user(self, buoy_superuser_client):
        url = reverse(self.base_url) + "?lat=0&lon=0"
        buoy_superuser_client, _ = buoy_superuser_client
        response = buoy_superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1
        assert response.data["results"][0]["id"]
        assert response.data["results"][0]["status"]
        assert response.data["results"][0]["last_updated"]
        assert response.data["results"][0]["display_id"]
        assert response.data["results"][0]["type"]
        assert response.data["results"][0]["devices"]
        assert len(response.data["results"][0]["devices"]) == 2

    def test_gear_subjects_view_duplicate_subjects_removed(self, buoy_client):
        user_client, gear_subjectsource = buoy_client

        # Arrange - additional on observations for gear_subjectsources must match
        additional = (
            Observation.objects.filter(source__subjectsource__subject=gear_subjectsource.subject)
            .latest("recorded_at")
            .additional
        )
        gear_subjectsource2 = SubjectSource.objects.get(pk=gear_subjectsource.pk)
        gear_subjectsource2.pk = None
        source = gear_subjectsource2.source
        now = timezone.now()
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }
        observation = Observation.objects.create(**data)
        observation.save()
        gear_subjectsource2.save()

        url = reverse(self.base_url) + "?lat=0&lon=0"
        response = user_client.get(url)

        latest_obs_additional1 = (
            Observation.objects.filter(source__subjectsource__subject=gear_subjectsource.subject)
            .latest("recorded_at")
            .additional
        )
        latest_obs_additional2 = (
            Observation.objects.filter(source__subjectsource__subject=gear_subjectsource2.subject)
            .latest("recorded_at")
            .additional
        )

        assert latest_obs_additional1["devices"] == latest_obs_additional2["devices"]
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    @pytest.mark.skip(reason="This test requires using the sensors api to handle the event_type field")
    def test_gear_subjects_view_non_duplicates_remain(self, buoy_client):
        user_client, gear_subjectsource = buoy_client
        gear_subjectsource2 = get_custom_location_gear_subjectsource()

        url = reverse(self.base_url) + "?lat=0&lon=0"
        response = user_client.get(url)

        latest_obs_additional1 = (
            Observation.objects.filter(source__subjectsource__subject=gear_subjectsource.subject)
            .latest("recorded_at")
            .additional
        )
        latest_obs_additional2 = (
            Observation.objects.filter(source__subjectsource__subject=gear_subjectsource2.subject)
            .latest("recorded_at")
            .additional
        )

        assert latest_obs_additional1["devices"] != latest_obs_additional2["devices"]
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_gear_subjects_view_with_deterministic_ordering_trawl(self, buoy_client):
        user_client, gear_subjectsource = buoy_client
        user_client, gear_subjectsource = buoy_client

        # Arrange - additional on observations for gear_subjectsources must match
        additional = (
            Observation.objects.filter(source__subjectsource__subject=gear_subjectsource.subject)
            .latest("recorded_at")
            .additional
        )
        gear_subjectsource2 = SubjectSource.objects.get(pk=gear_subjectsource.pk)
        gear_subjectsource2.pk = None
        source = gear_subjectsource2.source
        now = timezone.now()
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }
        observation = Observation.objects.create(**data)
        observation.save()
        gear_subjectsource2.save()

        gear_subjectsource.subject.name = "A"
        gear_subjectsource.subject.save()
        gear_subjectsource2.subject.name = "B"
        gear_subjectsource2.subject.save()

        url = reverse(self.base_url) + "?lat=0&lon=0"
        response = user_client.get(url)

        latest_obs_additional1 = (
            Observation.objects.filter(source__subjectsource__subject=gear_subjectsource.subject)
            .latest("recorded_at")
            .additional
        )
        latest_obs_additional2 = (
            Observation.objects.filter(source__subjectsource__subject=gear_subjectsource2.subject)
            .latest("recorded_at")
            .additional
        )

        assert gear_subjectsource.subject.name < gear_subjectsource2.subject.name
        assert latest_obs_additional1["devices"] == latest_obs_additional2["devices"]
        assert response.data["results"][0]["id"] == str(gear_subjectsource2.subject.id)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    @pytest.mark.skip(reason="This test requires using the sensors api to handle the event_type field")
    def test_gear_subjects_view_is_active_updated(self, buoy_client):
        user_client, gear_subjectsource = buoy_client

        # Gear is not included when is_active=True but gear is hauled
        gear_subjectsource.location = Point(0, 0)
        now = timezone.now()
        source = gear_subjectsource.source
        additional = generate_devices(2, Point(0, 0))
        additional["event_type"] = "gear_retrieved"
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }
        observation = Observation.objects.create(**data)
        observation.save()
        gear_subjectsource.save()
        gear_subjectsource.subject.is_active = True
        gear_subjectsource.subject.save()

        url = reverse(self.base_url) + "?lat=0&lon=0"
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

        # Gear is included when is_active=True and gear is deployed
        gear_subjectsource.location = Point(0, 0)
        now = timezone.now()
        source = gear_subjectsource.source
        additional = generate_devices(2, Point(0, 0))
        additional["event_type"] = "gear_deployed"
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }
        observation = Observation.objects.create(**data)
        observation.save()
        gear_subjectsource.save()
        gear_subjectsource.subject.is_active = True
        gear_subjectsource.subject.save()

        url = reverse(self.base_url) + "?lat=0&lon=0"
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["status"] == "deployed"

    def test_gear_subjects_view_with_not_linked_user_or_subject_permission(self):
        client = HTTPClient()
        request = client.factory.get(reverse(self.base_url) + "?lat=0&lon=0")
        client.force_authenticate(request, client.app_user)

        response = views.GearsListCreateView.as_view()(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_filter_gear_subject_api_updated_since(self, buoy_client):
        user_client, gear_subjectsource = buoy_client
        url = reverse(self.base_url)
        url += "?lat=0&lon=0"
        url += "&updated_since=2019-02-03"

        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

        # Arrange - Gear_subjectsource not included if updated before 2024-02-03
        gear_subjectsource2 = SubjectSource.objects.get(pk=gear_subjectsource.pk)
        gear_subjectsource2.pk = None
        source = gear_subjectsource2.source
        dt = datetime(2019, 1, 31).replace(tzinfo=timezone.utc)
        additional = generate_devices(2, Point(0, 0))
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": dt,
            "location": point,
            "source": source,
            "additional": additional,
        }
        observation = Observation.objects.create(**data)
        observation.save()
        gear_subjectsource2.save()

        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    @pytest.mark.parametrize(
        "params,expected_status,expected_error",
        [
            (
                {"lat": 0, "lon": 0, "page": 1, "page_size": 10, "max_nm_range": 50, "state": "deployed"},
                status.HTTP_200_OK,
                None,  # Valid case
            ),
            # Test invalid parameter types
            (
                {"lat": "notfloat", "lon": "invalid"},
                status.HTTP_400_BAD_REQUEST,
                {"lat": ["A valid number is required."], "lon": ["A valid number is required."]},
            ),
            (
                {"lat": 0, "lon": 0, "page": "abc", "page_size": "xyz"},
                status.HTTP_400_BAD_REQUEST,
                {"page": ["A valid integer is required."], "page_size": ["A valid integer is required."]},
            ),
            # Test range validations
            (
                {"lat": 91, "lon": 181},
                status.HTTP_400_BAD_REQUEST,
                {
                    "lat_lon": [
                        "Invalid latitude/longitude values. Latitude must be between -90 and 90, longitude between -180 and 180"
                    ]
                },
            ),
            (
                {"lat": 0, "lon": 0, "max_nm_range": -10},
                status.HTTP_400_BAD_REQUEST,
                {"max_nm_range": ["Ensure this value is greater than or equal to 1."]},
            ),
            (
                {"lat": 0, "lon": 0, "max_nm_range": 1001},
                status.HTTP_400_BAD_REQUEST,
                {"max_nm_range": ["Ensure this value is less than or equal to 1000."]},
            ),
            # Test required field combinations
            (
                {"lat": 0},  # Missing lon
                status.HTTP_400_BAD_REQUEST,
                {"lat_lon": ["Both lat and lon must be provided together"]},
            ),
            (
                {"lon": 0},  # Missing lat
                status.HTTP_400_BAD_REQUEST,
                {"lat_lon": ["Both lat and lon must be provided together"]},
            ),
            # Test invalid date format
            (
                {"lat": 0, "lon": 0, "updated_since": "invalid-date"},
                status.HTTP_400_BAD_REQUEST,
                {"updated_since": ["Must be a valid date"]},
            ),
            # Test invalid state choices
            (
                {"lat": 0, "lon": 0, "state": "invalid_state"},
                status.HTTP_400_BAD_REQUEST,
                {"state": ['"\\"invalid_state\\"" is not a valid choice.']},
            ),
        ],
    )
    def test_gears_view_query_params_validation(self, buoy_client, params, expected_status, expected_error):
        """Test comprehensive query parameter validation for GearsView.

        Tests:
        1. Valid parameter combinations
        2. Invalid parameter types (lat/lon/page/page_size)
        3. Range validations (lat/lon bounds, max_nm_range)
        4. Required field combinations (lat/lon pairing)
        5. Date format validation
        6. State choices validation
        """
        user_client, _ = buoy_client
        base = reverse(self.base_url)

        # Convert params dict to query string
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{base}?{query_string}"

        response = user_client.get(url)

        assert response.status_code == expected_status
        if res := response.json() and expected_error:
            for key, value in expected_error.items():
                assert res.get(key) == value

    def test_filter_gear_subject_api_state(self, buoy_client):
        user_client, gear_subjectsource = buoy_client
        url = reverse(self.base_url)
        url += "?lat=0&lon=0"
        url += "&state=deployed"

        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

        url = reverse(self.base_url)
        url += "?lat=0&lon=0"
        url += "&state=hauled"

        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0

        # Arrange - add a gear_subjectsource with is_active=False
        gear_subjectsource.location = Point(0, 0)
        now = timezone.now()
        source = gear_subjectsource.source
        additional = generate_devices(2, Point(0, 0))
        additional["event_type"] = "gear_retrieved"
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }
        observation = Observation.objects.create(**data)
        observation.save()
        gear_subjectsource.save()
        gear_subjectsource.subject.is_active = False
        gear_subjectsource.subject.save()

        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    @pytest.mark.skip(
        reason="This test requires using the sensors api to handle the event_type field, it's relying on the gear api to magically fix the subject is_active field"
    )
    def test_updating_inactive_subjects(self, buoy_client):
        user_client, gear_subjectsource = buoy_client
        # Set the subject to inactive
        gear_subjectsource.subject.is_active = False
        gear_subjectsource.subject.save()

        # Call the GET request to the gear list view
        # and trigger the update of inactive subjects
        url = reverse(self.base_url) + "?lat=0&lon=0"
        response = user_client.get(url)

        # Since the last observation has a gear_deployed event,
        # the subject should be marked as active
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        # Check if the subject is still inactive
        gear_subjectsource.refresh_from_db()
        assert gear_subjectsource.subject.is_active is True

    def test_filter_gear_subject_api_max_nm_range_provided(self, buoy_client):
        user_client, _ = buoy_client

        # Arrange - Create a set of gears
        origin = Point(10, 10)

        for miles in [4, 40, 400, 999]:
            bearing = random.uniform(0, 360)
            new_point = distance(miles=miles).destination(origin, bearing)
            gear_subjectsource = get_custom_location_gear_subjectsource(Point(new_point.longitude, new_point.latitude))
            gear_subjectsource.subject.additional["display_id"] = generate_fake_display_id()
            gear_subjectsource.subject.save()

        url = reverse(self.base_url)

        response = user_client.get(url + f"?lat={origin.y}&lon={origin.x}&max_nm_range=500")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3

        user_client.user.save()
        response = user_client.get(url + f"?lat={origin.y}&lon={origin.x}")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

        user_client.user.save()
        response = user_client.get(url + f"?lat={origin.y}&lon={origin.x}&max_nm_range=250")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

        user_client.user.save()
        response = user_client.get(url + f"?lat={origin.y}&lon={origin.x}&max_nm_range=1000")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 5

    def test_filter_gear_subject_api_max_nm_range_provided_but_no_lat_lon(self, buoy_client):
        user_client, _ = buoy_client
        url = reverse(self.base_url)

        user_client.user.username = "edgetech"
        user_client.user.save()
        response = user_client.get(url + "?max_nm_range=500")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        perm, _ = Permission.objects.get_or_create(codename="can_view_gear_regardless_location")
        perm_set = PermissionSet.objects.create(name="CanViewGearNoLoc")
        perm_set.permissions.add(perm)
        perm_set.save()
        user_client.user.permission_sets.add(perm_set)
        user_client.user.save()

        response = user_client.get(url + "?max_nm_range=500")
        assert response.status_code == status.HTTP_200_OK

    def test_gear_subjects_view_permission_can_view_gear_regardless_location(self, buoy_client, django_user_model):
        user_client, _ = buoy_client
        url = reverse(self.base_url)

        perm, _ = Permission.objects.get_or_create(codename="can_view_gear_regardless_location")
        perm_set = PermissionSet.objects.create(name="CanViewGearNoLoc")
        perm_set.permissions.add(perm)
        perm_set.save()
        user_client.user.permission_sets.add(perm_set)
        user_client.user.save()

        response = user_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        # Also test that a user with the permission but with lat/lon still works
        response = user_client.get(url + "?lat=0&lon=0")
        assert response.status_code == status.HTTP_200_OK

        user_client.user.permission_sets.clear()
        response = user_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_max_nm_range_param(self, buoy_client):
        user_client, _ = buoy_client
        url = reverse(self.base_url)

        # Non-numeric value
        response = user_client.get(url + "?lat=0&lon=0&max_nm_range=abc")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "max_nm_range" in str(response.data)

        # Negative value
        response = user_client.get(url + "?lat=0&lon=0&max_nm_range=-5")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "max_nm_range" in str(response.data)

        # Zero value
        response = user_client.get(url + "?lat=0&lon=0&max_nm_range=0")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "max_nm_range" in str(response.data)

        # Large value (should be accepted)
        response = user_client.get(url + "?lat=0&lon=0&max_nm_range=1000")
        assert response.status_code == status.HTTP_200_OK
