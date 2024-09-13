import pytest
import json

from django.urls import reverse
from django.utils import timezone
from django.contrib.gis.geos import Point
from django.contrib.auth.models import Permission
from rest_framework import status

from accounts.models import PermissionSet
from buoy import views
from observations.models import (
    Observation,
    Source,
    Subject,
    SubjectGroup,
    SubjectSource
)
from client_http import HTTPClient
from das.buoy.tests import generate_devices
from factories import GearFactory
from utils.tenant.dataclass import FeatureFlags


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.skipif(FeatureFlags.buoy_api_enabled is False, reason="Buoy API feature flag is off")
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
        assert response.data["id"] == str(user.linked_subject.id)
        assert response.data["display_id"] == user.linked_subject.name
        assert response.data["status"] == "deployed"
        assert response.data["last_updated"]

    def test_subject_view_with_linked_user_and_not_subject_permission(self, _get_client):
        response, user = _get_client
        assert response.data["id"] == str(user.linked_subject.id)

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
@pytest.mark.skipif(FeatureFlags.buoy_api_enabled is False, reason="Buoy API feature flag is off")
class TestGearsView:
    base_url = "gear-list-view"
    
    @pytest.fixture
    def gear_super_subjectsource(self):
        gear_subjectsource = GearFactory.create()
        gear_subjectsource.save()

        source = gear_subjectsource.source
        provider = gear_subjectsource.source.provider
        provider.save()
        now = timezone.now()
        additional = generate_devices(2)
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

        return gear_subjectsource
    
    @pytest.fixture
    def buoy_superuser_client(self, gear_super_subjectsource, superuser_client):
        gear_super_subjectsource.linked_user = superuser_client.user
        gear_super_subjectsource.save()
        return superuser_client
    
    @pytest.fixture
    def buoy_client(self, gear_super_subjectsource, user_client):
        gear_super_subjectsource.linked_user = user_client.user

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
        parent_group.subjects.add(gear_super_subjectsource.subject)
        parent_group.is_visible = True
        parent_group.save()

        gear_super_subjectsource.save()
        return user_client, gear_super_subjectsource

    @pytest.fixture
    def _get_client(self, gear_super_subjectsource):
        client = HTTPClient()
        gear_super_subjectsource.linked_user = client.app_user
        gear_super_subjectsource.save()
        request = client.factory.get(reverse(self.base_url))
        client.force_authenticate(request, client.app_user)

        return views.GearsView.as_view()(request), client.app_user

    def test_gear_subjects_view_with_linked_user(self, buoy_client):
        url = reverse(self.base_url)
        user_client, _ = buoy_client
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_gear_subjects_view_without_linked_user(self, buoy_superuser_client):
        url = reverse(self.base_url)
        response = buoy_superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        assert response.data["results"][0]["id"]
        assert response.data["results"][0]["status"]
        assert response.data["results"][0]["last_updated"]
        assert response.data["results"][0]["display_id"]
        assert response.data["results"][0]["type"]
        assert response.data["results"][0]["devices"]
        assert len(response.data["results"][0]["devices"]) == 2

    def test_gear_subjects_view_duplicate_subjects_removed(self, buoy_client):
        user_client, gear_subjectsource = buoy_client
        additional = Observation.objects.filter(source__subjectsource__subject=gear_subjectsource.subject).latest("recorded_at").additional

        gear_subjectsource2 = SubjectSource.objects.get(pk=gear_subjectsource.pk)
        gear_subjectsource2.pk = None

        source = gear_subjectsource2.source
        provider = gear_subjectsource2.source.provider
        provider.save()
        now = timezone.now()
        additional2 = additional
        location_dict = json.loads(additional2["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional2,
        }
        observation = Observation.objects.create(**data)
        observation.save()
        gear_subjectsource2.save()

        url = reverse(self.base_url)
        response = user_client.get(url)

        assert additional["devices"] == additional2["devices"]
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_gear_subjects_view_non_duplicates_remain(self, buoy_client):
        user_client, gear_subjectsource = buoy_client
        gear_subjectsource2 = SubjectSource.objects.get(pk=gear_subjectsource.pk)

        gear_subjectsource2.pk = None
        source = Source.objects.create(manufacturer_id="000")
        source.save()
        gear_subjectsource2.source = source
        gear_subjectsource2.save()
        provider = gear_subjectsource2.source.provider
        provider.save()
        now = timezone.now()
        subject = Subject.objects.create(name="New Subject")
        subject.save()
        gear_subjectsource2.subject = subject
        gear_subjectsource2.save()
        additional2 = generate_devices(2)
        location_dict = json.loads(additional2["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional2,
        }
        observation = Observation.objects.create(**data)
        observation.save()
        gear_subjectsource2.save()

        url = reverse(self.base_url)
        response = user_client.get(url)

        latest_obs_additional1 = Observation.objects.filter(source__subjectsource__subject=gear_subjectsource.subject).latest("recorded_at").additional
        latest_obs_additional2 = Observation.objects.filter(source__subjectsource__subject=gear_subjectsource2.subject).latest("recorded_at").additional

        assert latest_obs_additional1["devices"] != latest_obs_additional2["devices"]
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_gear_subjects_view_with_not_linked_user_or_subject_permission(self):
        client = HTTPClient()
        request = client.factory.get(reverse(self.base_url))
        client.force_authenticate(request, client.app_user)

        response = views.GearsView.as_view()(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN

