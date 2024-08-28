import pytest

from django.urls import reverse
from rest_framework import status

from client_http import HTTPClient
from das.buoy.tests.test_serializers import generate_devices
from das.buoy.views import GearView
from utils.tenant.dataclass import FeatureFlags


@pytest.mark.django_db
@pytest.mark.usefixtures("gear_subject")
@pytest.mark.skipif(FeatureFlags.buoy_api_enabled is False, reason="Buoy API feature flag is off")
class TestGearSubjectView:
    base_url = "gear-view"

    # @pytest.fixture
    # def _get_superuser_client(self, gear_subject, superuser, superuser_client):
    #     url = reverse(self.base_url, kwargs={"id": gear_subject.id})
    #     gear_subject.linked_user = superuser
    #     gear_subject.additional = generate_devices(2)
    #     gear_subject.save()
    #     return superuser_client.get(url), superuser

    @pytest.fixture
    def _get_client(self, gear_subject):
        client = HTTPClient()
        gear_subject.linked_user = client.app_user
        gear_subject.additional = generate_devices(2)
        gear_subject.save()
        url = reverse(self.base_url, kwargs={"id": gear_subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        return GearView.as_view()(request, id=str(gear_subject.id)), client.app_user

    def test_single_gear_subject_view(self, _get_client):
        response, _ = _get_client
        assert response.data["id"]
        assert len(response.data["devices"]) == 2

    def test_gear_subject_view_with_linked_user_and_not_subject_permission(self, _get_client):
        response, _ = _get_client
        assert response.data["id"]
        assert len(response.data["devices"]) == 2

    # def test_gear_subject_view_without_linked_user(self, _get_superuser_client):
    #     response, _ = _get_superuser_client
    #     assert not hasattr(response.data, "user")

    def test_gear_subject_view_with_not_linked_user_or_subject_permission(self, gear_subject):
        client = HTTPClient()
        url = reverse("gear-view", kwargs={"id": gear_subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        response = GearView.as_view()(request, id=str(gear_subject.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    # def test_gear_subject_view_with_linked_user_ask_for_random_subject(self, five_gears, superuser_client, superuser):
    #     subject1 = five_gears[0]
    #     subject2 = five_gears[1]
    #     url = reverse("gear-view", kwargs={"id": subject2.id})
    #     subject1.linked_user = superuser
    #     subject1.save()
    #     response = superuser_client.get(url)

    #     assert response.status_code == status.HTTP_200_OK

    #     assert response.data["id"] == str(subject2.id)


# @pytest.mark.django_db
# @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
# class TestSubjectsView:
#     base_url = "gear-list-view"

#     @pytest.fixture
#     def _get_superuser_client(self, subject, superuser, superuser_client):
#         subject.linked_user = superuser
#         subject.save()
#         return superuser_client.get(reverse(self.base_url)), superuser

#     @pytest.fixture
#     def _get_client(self, subject):
#         client = HTTPClient()
#         subject.linked_user = client.app_user
#         subject.save()
#         request = client.factory.get(reverse(self.base_url))
#         client.force_authenticate(request, client.app_user)

#         return views.SubjectsView.as_view()(request), client.app_user

#     def test_subjects_view_with_linked_user(self, memory_store_client_mock, _get_superuser_client):
#         response, user = _get_superuser_client
#         assert response.data[0]["user"]["id"] == str(user.id)

#     def test_subjects_view_without_linked_user(self, memory_store_client_mock, _get_superuser_client):
#         response, _ = _get_superuser_client

#         assert not hasattr(response.data[0], "user")

#     def test_subjects_view_with_linked_user_and_not_subject_permission(self, _get_client):
#         response, user = _get_client

#         assert response.data[0]["user"]["id"] == str(user.id)

#     def test_subjects_view_with_not_linked_user_or_subject_permission(self):
#         client = HTTPClient()
#         request = client.factory.get(reverse("subjects-list-view"))
#         client.force_authenticate(request, client.app_user)

#         response = views.SubjectsView.as_view()(request)

#         assert response.status_code == status.HTTP_403_FORBIDDEN
