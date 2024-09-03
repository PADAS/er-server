import pytest

from django.urls import reverse
from rest_framework import status

from buoy import views
from client_http import HTTPClient
from das.buoy.tests.test_serializers import generate_devices
from factories import GearFactory
from utils.tenant.dataclass import FeatureFlags


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.skipif(FeatureFlags.buoy_api_enabled is False, reason="Buoy API feature flag is off")
class TestGearView:
    base_url = "gear-view"

    @pytest.fixture
    def gear_super_subject(self):
        return GearFactory.create()

    @pytest.fixture
    def buoy_superuser_client(self, gear_super_subject, superuser_client):
        gear_super_subject.linked_user = superuser_client.user
        gear_super_subject.additional = generate_devices(2)
        gear_super_subject.save()
        return superuser_client

    @pytest.fixture
    def buoy_client(self, gear_subject, user_client):
        gear_subject.linked_user = user_client.user
        gear_subject.additional = generate_devices(2)
        gear_subject.save()
        return user_client

    def test_single_gear_subject_view(self, buoy_client):
        url = reverse(self.base_url, kwargs={"id": str(buoy_client.user.linked_subject.id)})
        response = buoy_client.get(url)

        assert response.data["id"]
        assert len(response.data["devices"]) == 2

    def test_gear_subject_view_with_linked_user_and_not_subject_permission(self, buoy_superuser_client, buoy_client):
        url = reverse(self.base_url, kwargs={"id": str(buoy_superuser_client.user.linked_subject.id)})
        response = buoy_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_gear_subject_view_without_linked_user(self, superuser_client, gear_subject):
        url = reverse(self.base_url, kwargs={"id": str(gear_subject.id)})
        response = superuser_client.get(url)
        assert not hasattr(response.data, "user")

    def test_gear_subject_view_with_not_linked_user_or_subject_permission(self, user_client, gear_subject):
        url = reverse(self.base_url, kwargs={"id": gear_subject.id})
        response = user_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_gear_subject_view_with_linked_user_ask_for_random_subject(self, five_gears, superuser_client, superuser):
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
    def gear_super_subject(self):
        return GearFactory.create()
    
    @pytest.fixture
    def buoy_superuser_client(self, gear_super_subject, superuser_client):
        gear_super_subject.linked_user = superuser_client.user
        gear_super_subject.additional = generate_devices(2)
        gear_super_subject.save()
        return superuser_client
    
    @pytest.fixture
    def buoy_client(self, gear_subject, user_client):
        gear_subject.linked_user = user_client.user
        gear_subject.additional = generate_devices(2)
        gear_subject.save()
        return user_client

    def test_gear_subjects_view_with_linked_user(self, buoy_client):
        url = reverse(self.base_url)
        response = buoy_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_gear_subjects_view_without_linked_user(self, buoy_superuser_client):
        url = reverse(self.base_url)
        response = buoy_superuser_client.get(url)

        assert not hasattr(response.data[0], "user")

    def test_gear_subjects_view_with_linked_user_and_not_subject_permission(self, buoy_client):
        url = reverse(self.base_url)
        response = buoy_client.get(url)

        assert response.data[0]["id"]
        assert len(response.data[0]["devices"]) == 2

    def test_gear_subjects_view_with_not_linked_user_or_subject_permission(self):
        client = HTTPClient()
        request = client.factory.get(reverse(self.base_url))
        client.force_authenticate(request, client.app_user)

        response = views.GearsView.as_view()(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN

