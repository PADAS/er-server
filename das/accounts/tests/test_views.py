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

    def test_get_user_no_modified(self, superuser_client):
        user = User.objects.last()
        url = reverse("accounts:user", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()

        etag = response.headers["ETag"]
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert etag == new_response.headers["Etag"]

    def test_modified_user(self, superuser_client) -> None:
        user = User.objects.last()
        url = reverse("accounts:user", kwargs={"id": str(user.id)})
        response = superuser_client.get(url)

        etag = response.headers["ETag"]

        user.first_name = "New Name"
        user.save(update_fields=("first_name",))

        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert etag != new_response.headers["Etag"]


@pytest.mark.django_db
class TestUserProfilesView:
    def test_get_empty_list_of_profiles_by_user(self, superuser_client):
        user = User.objects.last()
        url = reverse("accounts:user-profiles", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
        assert "ETag" in response.headers.keys()

    def test_get_user_profiles_not_modified_by_user(self, superuser_client, superuser, five_users):
        profile_user = five_users[0]
        user = superuser
        user.act_as_profiles.add(profile_user)
        user.save()

        url = reverse("accounts:user-profiles", kwargs={"id": str(user.id)})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        etag = response.headers["ETag"]

        url = reverse("accounts:user-profiles", kwargs={"id": str(user.id)})
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert etag == new_response.headers["Etag"]

    def test_get_user_profiles_modified_by_user(self, superuser_client, superuser, five_users):
        profile_user = five_users[1]
        superuser.act_as_profiles.add(profile_user)
        superuser.save()

        url = reverse("accounts:user-profiles", kwargs={"id": str(superuser.id)})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        superuser.act_as_profiles.add(five_users[2])
        superuser.save()
        etag = response.headers["ETag"]

        url = reverse("accounts:user-profiles", kwargs={"id": str(superuser.id)})
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_200_OK
        assert etag != new_response.headers["Etag"]
