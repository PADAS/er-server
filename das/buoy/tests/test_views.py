import json
import random
from datetime import datetime, timedelta

import pytest
from geopy.distance import distance
from psycopg2.extras import DateTimeTZRange

from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.models import PermissionSet
from buoy import views
from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from client_http import HTTPClient
from das.buoy.tests import (
    generate_devices,
    generate_fake_display_id,
    get_custom_location_gear_subjectsource,
)
from observations.models import (
    DEFAULT_ASSIGNED_RANGE,
    EMPTY_POINT,
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectGroup,
    SubjectSource,
    SubjectSubType,
    SubjectType,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearView:
    base_url = "gear-view"

    @pytest.fixture
    def _get_superuser_client(self, gear_subjectsource, superuser, superuser_client):
        url = reverse(self.base_url, kwargs={"id": gear_subjectsource.subject.id})
        # Create SubjectGroup and add subject to it
        subject_group = SubjectGroup.objects.create(name="SuperUserManufacturer")
        gear_subjectsource.subject.groups.add(subject_group)

        # Assign permission to superuser
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser.permission_sets.add(permission_set)

        return superuser_client.get(url), superuser

    @pytest.fixture
    def _get_client(self, gear_subjectsource):
        client = HTTPClient()
        # Create SubjectGroup and add subject to it
        subject_group = SubjectGroup.objects.create(name="RegularUserManufacturer")
        gear_subjectsource.subject.groups.add(subject_group)

        # Assign permission to user
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        client.app_user.permission_sets.add(permission_set)

        url = reverse(self.base_url, kwargs={"id": gear_subjectsource.subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        return views.GearView.as_view()(request, id=str(gear_subjectsource.subject.id)), client.app_user

    def test_subject_view_with_matching_source_provider(self, _get_superuser_client):
        response, user = _get_superuser_client
        # GearSerializer returns SubjectSource, so id comes from subject.id
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"]
        assert response.data["status"] == "deployed"
        assert response.data["last_updated"]

    def test_subject_view_with_matching_source_provider_regular_user(self, _get_client):
        response, user = _get_client
        # Should have access since user has permission to the SubjectGroup
        assert response.status_code == 200
        assert response.data["id"]

    def test_subject_view_without_matching_source_provider(self, gear_subjectsource):
        client = HTTPClient()
        # Don't add subject to any SubjectGroup that user has access to - permission should be denied
        url = reverse(self.base_url, kwargs={"id": gear_subjectsource.subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        response = views.GearView.as_view()(request, id=str(gear_subjectsource.subject.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_subject_view_with_not_matching_source_provider(self, gear_subjectsource):
        client = HTTPClient()
        # Create SubjectGroup but don't assign permission to user
        subject_group = SubjectGroup.objects.create(name="OtherManufacturer")
        gear_subjectsource.subject.groups.add(subject_group)

        url = reverse(self.base_url, kwargs={"id": gear_subjectsource.subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        response = views.GearView.as_view()(request, id=str(gear_subjectsource.subject.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_subject_view_different_subject_with_different_provider(self, five_gears, user_client, django_user_model):
        # Create a regular user (not superuser)
        user = django_user_model.objects.create_user(username="regular_user", password="testpass")

        subject1_source = five_gears[0]
        subject2_source = five_gears[1]

        # Create and assign distinct SubjectGroups for each subject to ensure isolation
        subject_group1 = SubjectGroup.objects.create(name="Manufacturer1")
        subject1_source.subject.groups.add(subject_group1)
        permission_set1, _ = PermissionSet.objects.get_or_create(name=subject_group1.auto_permissionset_name)
        subject_group1.permission_sets.add(permission_set1)
        user.permission_sets.add(permission_set1)

        subject_group2 = SubjectGroup.objects.create(name="Manufacturer2")
        subject2_source.subject.groups.add(subject_group2)
        # Don't give user access to subject_group2

        # Assert SubjectGroups are different to catch fixture misconfiguration
        assert subject_group1.id != subject_group2.id, "Test requires different SubjectGroups for subjects"

        # Try to access subject2 - should be denied
        url = reverse(self.base_url, kwargs={"id": subject2_source.subject.id})
        user_client.force_authenticate(user=user)
        response = user_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearsView:

    base_url = "gear-list-create-view"

    @pytest.fixture
    def buoy_superuser_client(self, gear_subjectsource_with_observations, superuser_client):
        # Create SubjectGroup and add subject to it
        subject_group = SubjectGroup.objects.create(name="SuperUserTestManufacturer")
        gear_subjectsource_with_observations.subject.groups.add(subject_group)

        # Assign permission to superuser
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser_client.user.permission_sets.add(permission_set)

        return superuser_client, gear_subjectsource_with_observations

    @pytest.fixture
    def buoy_client(self, gear_subjectsource_with_observations, user_client):
        # Create SubjectGroup and add subject to it
        subject_group = SubjectGroup.objects.create(name="UserTestManufacturer")
        gear_subjectsource_with_observations.subject.groups.add(subject_group)

        # Assign permission to user
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        user_client.user.permission_sets.add(permission_set)

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

    def test_trawl_gear_appears_once_in_list(self, buoy_client):
        """A trawl gearset (one Subject with two Sources/SubjectSources) must appear
        exactly once in the list response, not once per device."""
        user_client, gear_subjectsource = buoy_client
        subject = gear_subjectsource.subject
        provider = gear_subjectsource.source.provider
        now = timezone.now()

        # Add a second device (Source + SubjectSource) to the same gearset Subject
        source2 = Source.objects.create(manufacturer_id="trawl_device_002", provider=provider)
        location2 = Point(-24.44, 31.20)
        SubjectSource.objects.create(
            subject=subject,
            source=source2,
            assigned_range=DateTimeTZRange(now, None),
            location=location2,
        )

        url = reverse(self.base_url) + "?lat=0&lon=0"
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["id"] == str(subject.id)
        assert response.data["results"][0]["type"] == "trawl"
        assert len(response.data["results"][0]["devices"]) == 2

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

    def test_two_distinct_gearsets_both_appear_in_list(self, buoy_client):
        """Two separate gearset Subjects must each appear as their own result."""
        user_client, gear_subjectsource = buoy_client
        subject1 = gear_subjectsource.subject
        subject_subtype = subject1.subject_subtype
        provider = gear_subjectsource.source.provider
        now = timezone.now()

        # Create a second independent gearset with its own subject and source
        source2 = Source.objects.create(manufacturer_id="second_gear_device", provider=provider)
        subject2 = Subject.objects.create(
            name="Second_Gearset",
            subject_subtype=subject_subtype,
            is_active=True,
        )
        SubjectSource.objects.create(
            subject=subject2,
            source=source2,
            assigned_range=DateTimeTZRange(now, None),
            location=Point(0.01, 0.01),
        )

        # Create observation so bbox filter finds source2 (DB trigger populates LatestObservationSource)
        Observation.objects.create(
            recorded_at=now,
            location=Point(0.01, 0.01),
            source=source2,
        )

        # Give the user permission to see subject2 via the same SubjectGroup
        subject_group = SubjectGroup.objects.filter(subjects=subject1).first()
        assert subject_group, "Fixture must create a SubjectGroup for subject1"
        subject_group.subjects.add(subject2)

        url = reverse(self.base_url) + "?lat=0&lon=0"
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        result_ids = {r["id"] for r in response.data["results"]}
        assert str(subject1.id) in result_ids
        assert str(subject2.id) in result_ids
        assert len(response.data["results"]) == 2

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
            # Test inexistent parameters
            (
                {"invalid": 0, "inexistant": 1},
                status.HTTP_403_FORBIDDEN,
                {"detail": ["You do not have permission to perform this action."]},
            ),
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
        user_client, gear_subjectsource = buoy_client

        # Get the SubjectGroup that the user has access to
        subject_group = SubjectGroup.objects.get(name="UserTestManufacturer")

        # Arrange - Create a set of gears
        origin = Point(10, 10)

        for miles in [4, 40, 400, 999]:
            bearing = random.uniform(0, 360)
            new_point = distance(miles=miles).destination(origin, bearing)
            gear_subjectsource_new = get_custom_location_gear_subjectsource(
                Point(new_point.longitude, new_point.latitude)
            )
            gear_subjectsource_new.subject.additional["display_id"] = generate_fake_display_id()
            gear_subjectsource_new.subject.save()
            # Add the gear to the SubjectGroup so the user can see it
            gear_subjectsource_new.subject.groups.add(subject_group)

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


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearsViewPostWithNullLocation:
    """Integration tests for POST to GearsListCreateView with null location data."""

    base_url = "gear-list-create-view"

    def test_post_gearset_with_edgetech_null_lat_lon_format(self, superuser_client):
        """Test POST with Edgetech format: location object with null latitude/longitude."""

        # Create SubjectGroup for EdgeTech
        subject_group = SubjectGroup.objects.create(name="EdgeTech")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser_client.user.permission_sets.add(permission_set)

        now = timezone.now()
        payload = {
            "set_id": "04a9431f-e4a0-414d-ae5f-b36cb4dc1a27",
            "owner_id": "652e7174c0884e7f02ec97d1",
            "manufacturer_name": "EdgeTech",
            "deployment_type": "trawl",
            "devices_in_set": 2,
            "initial_deployment_date": now.isoformat(),
            "devices": [
                {
                    "device_id": "a5f89d41-d119-4ece-b8f8-d6c8d96d2b40",
                    "mfr_device_id": "88CE99D7C3_test",
                    "last_deployed": now.isoformat(),
                    "last_updated": now.isoformat(),
                    "recorded_at": now.isoformat(),
                    "device_status": "deployed",
                    "location": {"latitude": 40.6014382, "longitude": -70.5142263},
                },
                {
                    "device_id": "f674e7ee-a7c7-4872-a1b9-e218741f9f70",
                    "mfr_device_id": "88CE99D9A9_test",
                    "last_deployed": now.isoformat(),
                    "last_updated": now.isoformat(),
                    "recorded_at": now.isoformat(),
                    "device_status": "deployed",
                    # Edgetech format: location object with null values
                    "location": {"latitude": None, "longitude": None},
                },
            ],
        }

        url = reverse(self.base_url)
        response = superuser_client.post(url, data=payload, format="json")

        assert (
            response.status_code == status.HTTP_201_CREATED
        ), f"Expected 201, got {response.status_code}: {response.data}"
        assert "set_id" in response.data
        assert response.data["set_id"] == "04a9431f-e4a0-414d-ae5f-b36cb4dc1a27"

        # Verify observations were created correctly
        obs_with_loc = Observation.objects.get(source_id="a5f89d41-d119-4ece-b8f8-d6c8d96d2b40")
        obs_null_loc = Observation.objects.get(source_id="f674e7ee-a7c7-4872-a1b9-e218741f9f70")

        assert obs_with_loc.location.x == -70.5142263
        assert obs_with_loc.location.y == 40.6014382
        assert obs_null_loc.location == EMPTY_POINT

        # Verify SubjectSource locations
        ss_with_loc = SubjectSource.objects.get(source_id="a5f89d41-d119-4ece-b8f8-d6c8d96d2b40")
        ss_null_loc = SubjectSource.objects.get(source_id="f674e7ee-a7c7-4872-a1b9-e218741f9f70")

        assert ss_with_loc.location is not None
        assert ss_null_loc.location is None


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearsViewIncludeEmptyLocation:
    """Tests for include_empty_location query parameter on GET /gears endpoint."""

    base_url = "gear-list-create-view"

    @pytest.fixture
    def gear_with_mixed_locations(self, superuser_client):
        """Create a gearset with one device having location and another with EMPTY_POINT."""

        # Ensure SubjectSubType exists for buoy gear
        subject_type, _ = SubjectType.objects.get_or_create(value="gear", defaults={"display": "Gear"})
        SubjectSubType.objects.get_or_create(
            value=BUOY_GEAR_SUBJECT_SUBTYPE, defaults={"display": "Ropeless Buoy Gearset", "subject_type": subject_type}
        )

        # Create SubjectGroup for EdgeTech
        subject_group = SubjectGroup.objects.create(name="EdgeTechEmptyLocTest")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser_client.user.permission_sets.add(permission_set)

        now = timezone.now()
        payload = {
            "set_id": "14a9431f-e4a0-414d-ae5f-b36cb4dc1a28",
            "owner_id": "test_owner",
            "manufacturer_name": "EdgeTechEmptyLocTest",
            "deployment_type": "trawl",
            "devices_in_set": 2,
            "initial_deployment_date": now.isoformat(),
            "devices": [
                {
                    "device_id": "b5f89d41-d119-4ece-b8f8-d6c8d96d2b41",
                    "mfr_device_id": "device_with_location",
                    "last_deployed": now.isoformat(),
                    "last_updated": now.isoformat(),
                    "recorded_at": now.isoformat(),
                    "device_status": "deployed",
                    "location": {"latitude": 40.6014382, "longitude": -70.5142263},
                },
                {
                    "device_id": "c674e7ee-a7c7-4872-a1b9-e218741f9f71",
                    "mfr_device_id": "device_without_location",
                    "last_deployed": now.isoformat(),
                    "last_updated": now.isoformat(),
                    "recorded_at": now.isoformat(),
                    "device_status": "deployed",
                    "location": {"latitude": None, "longitude": None},
                },
            ],
        }

        url = reverse(self.base_url)
        response = superuser_client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        return superuser_client, subject_group

    def test_get_gears_excludes_empty_location_devices_by_default(self, gear_with_mixed_locations):
        """Test that GET /gears excludes devices with EMPTY_POINT location by default."""

        superuser_client, subject_group = gear_with_mixed_locations

        # Give user permission to view gear regardless of location
        perm, _ = Permission.objects.get_or_create(codename="can_view_gear_regardless_location")
        perm_set = PermissionSet.objects.create(name="CanViewGearNoLocTest")
        perm_set.permissions.add(perm)
        superuser_client.user.permission_sets.add(perm_set)

        url = reverse(self.base_url)
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK, f"Expected 200, got {response.status_code}: {response.data}"
        results = response.data["results"]

        # Find our gear
        gear = next((g for g in results if g["id"] == "14a9431f-e4a0-414d-ae5f-b36cb4dc1a28"), None)
        assert gear is not None, f"Gear not found in results. All gear IDs: {[g['id'] for g in results]}"

        # Only device with location should be included
        assert len(gear["devices"]) == 1
        assert gear["devices"][0]["mfr_device_id"] == "device_with_location"
        assert gear["devices"][0]["location"]["latitude"] == 40.6014382

    def test_get_gears_includes_empty_location_devices_when_flag_true(self, gear_with_mixed_locations):
        """Test that GET /gears includes devices with EMPTY_POINT when include_empty_location=true."""

        superuser_client, subject_group = gear_with_mixed_locations

        # Give user permission to view gear regardless of location
        perm, _ = Permission.objects.get_or_create(codename="can_view_gear_regardless_location")
        perm_set = PermissionSet.objects.create(name="CanViewGearNoLocTest2")
        perm_set.permissions.add(perm)
        superuser_client.user.permission_sets.add(perm_set)

        url = reverse(self.base_url)
        response = superuser_client.get(url + "?include_empty_location=true")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        # Find our gear
        gear = next((g for g in results if g["id"] == "14a9431f-e4a0-414d-ae5f-b36cb4dc1a28"), None)
        assert gear is not None, f"Gear not found in results. All gear IDs: {[g['id'] for g in results]}"

        # Both devices should be included
        assert len(gear["devices"]) == 2

        device_ids = [d["mfr_device_id"] for d in gear["devices"]]
        assert "device_with_location" in device_ids
        assert "device_without_location" in device_ids

        # Device without location should have null lat/lon
        device_without_loc = next(d for d in gear["devices"] if d["mfr_device_id"] == "device_without_location")
        assert device_without_loc["location"]["latitude"] is None
        assert device_without_loc["location"]["longitude"] is None

    def test_get_gears_include_empty_location_false_explicit(self, gear_with_mixed_locations):
        """Test that include_empty_location=false explicitly excludes empty location devices."""

        superuser_client, subject_group = gear_with_mixed_locations

        # Give user permission to view gear regardless of location
        perm, _ = Permission.objects.get_or_create(codename="can_view_gear_regardless_location")
        perm_set = PermissionSet.objects.create(name="CanViewGearNoLocTest3")
        perm_set.permissions.add(perm)
        superuser_client.user.permission_sets.add(perm_set)

        url = reverse(self.base_url)
        response = superuser_client.get(url + "?include_empty_location=false")

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]

        # Find our gear
        gear = next((g for g in results if g["id"] == "14a9431f-e4a0-414d-ae5f-b36cb4dc1a28"), None)
        assert gear is not None, f"Gear not found in results. All gear IDs: {[g['id'] for g in results]}"

        # Only device with location should be included
        assert len(gear["devices"]) == 1
        assert gear["devices"][0]["mfr_device_id"] == "device_with_location"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearsViewOlderGearsetRejection:
    """View-level integration tests for the older-gearset rejection 400 path."""

    base_url = "gear-list-create-view"

    def test_post_older_gearset_returns_400_and_no_state_change(self, superuser_client):
        """POST with a device already deployed on a newer gearset returns 400 and commits no state changes."""
        subject_group = SubjectGroup.objects.create(name="OlderRejectViewManufacturer")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser_client.user.permission_sets.add(permission_set)

        subject_subtype, _ = SubjectSubType.objects.get_or_create(value=BUOY_GEAR_SUBJECT_SUBTYPE)
        provider = SourceProvider.objects.create(
            display_name="OlderRejectViewManufacturer",
            provider_key="gundi_olderrejectviewmanufacturer",
        )
        device_uuid = "aabbccdd-0000-4000-8000-000000000001"
        source = Source.objects.create(id=device_uuid, manufacturer_id="view_shared_device", provider=provider)

        # Existing (newer) gearset deployed at t_newer
        t_newer = timezone.now() - timedelta(hours=1)
        subject_newer = Subject.objects.create(name="NewerGearset", subject_subtype=subject_subtype, is_active=True)
        subject_newer.groups.add(subject_group)
        SubjectSource.objects.create(
            subject=subject_newer,
            source=source,
            assigned_range=DateTimeTZRange(lower=t_newer, upper=DEFAULT_ASSIGNED_RANGE[1]),
        )

        # Attempt to POST an older gearset (recorded_at before t_newer)
        t_older = t_newer - timedelta(hours=2)
        older_set_id = "aabbccdd-1111-4000-8000-000000000001"
        payload = {
            "set_id": older_set_id,
            "manufacturer_name": "OlderRejectViewManufacturer",
            "owner_id": "owner1",
            "mfr_set_id": "OLDER_SET",
            "deployment_type": "single",
            "initial_deployment_date": t_older.isoformat(),
            "devices": [
                {
                    "device_id": device_uuid,
                    "mfr_device_id": "view_shared_device",
                    "recorded_at": t_older.isoformat(),
                    "last_deployed": t_older.isoformat(),
                    "last_updated": t_older.isoformat(),
                    "device_status": "deployed",
                    "location": {"latitude": 1.0, "longitude": 2.0},
                }
            ],
        }

        url = reverse(self.base_url)
        response = superuser_client.post(url, data=payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # fixup_api_response moves "detail" into response.data["status"]["detail"]
        assert "device_id" in response.data
        assert "newer_gearset_id" in response.data
        assert "detail" in response.data.get("status", {})

        # Verify no state was committed: newer gearset must remain open and active
        subject_newer.refresh_from_db()
        assert subject_newer.is_active is True
        ss = SubjectSource.objects.get(subject=subject_newer, source=source)
        assert ss.assigned_range.upper == DEFAULT_ASSIGNED_RANGE[1]

        # The older gearset subject must not have been created
        assert not Subject.objects.filter(id=older_set_id).exists()
