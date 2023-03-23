import pytest

from django.urls import reverse
from rest_framework import status

from accounts.models import User


@pytest.mark.django_db
class TestUsersView:
    def test_get_list_of_users(self, superuser_client):
        url = reverse("accounts:users")

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Because das_oauth_act and superuser_client
        assert len(response.data) == 2


@pytest.mark.django_db
class TestUserView:
    def test_get_user(self, superuser_client):
        user = User.objects.last()
        url = reverse("accounts:user", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()


@pytest.mark.django_db
class TestUserProfilesView:
    def test_get_empty_list_of_profiles_by_user(self, superuser_client):
        user = User.objects.last()
        url = reverse("accounts:user-profiles", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
        assert "ETag" in response.headers.keys()
