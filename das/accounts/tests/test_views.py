import pytest

from django.urls import reverse
from rest_framework import status

from accounts.models import User


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUsersView:
    def test_get_list_of_users(self, superuser_client, memory_store_client_mock):
        url = reverse("accounts:users")

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Because das_oauth_act and user_client
        assert len(response.data) == User.objects.count()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUserView:
    def test_get_user(self, superuser_client, memory_store_client_mock):
        user = superuser_client.user
        url = reverse("accounts:user", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()

    def test_get_user_no_modified(self, superuser_client, memory_store_client_mock):
        user = superuser_client.user
        url = reverse("accounts:user", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()

        etag = response.headers["ETag"]
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert etag == new_response.headers["Etag"]

    def test_get_user_no_modified_profile_user(self, superuser_client, memory_store_client_mock, user):
        url = reverse("accounts:user", kwargs={"id": str(user.id)})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()

        etag = response.headers["ETag"]

        client = superuser_client
        client.credentials(USER_PROFILE=user)
        new_response = client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert etag == new_response.headers["Etag"]

    def test_get_user_with_profile_should_resolved(self, superuser_client, user) -> None:
        superuser = superuser_client.user
        superuser.act_as_profiles.add(user)

        url = reverse("accounts:user", kwargs={"id": "me"})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()
        etag = response.headers["ETag"]

        response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)
        etag = response.headers["ETag"]

        assert response.status_code == status.HTTP_304_NOT_MODIFIED

        response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag, HTTP_USER_PROFILE=str(user.id))
        assert response.status_code == status.HTTP_200_OK

    def test_modified_user_new_etag(self, superuser_client, memory_store_client_mock) -> None:
        user = superuser_client.user
        url = reverse("accounts:user", kwargs={"id": str(user.id)})
        response = superuser_client.get(url)

        etag = response.headers["ETag"]

        User.objects.filter(id=user.id).update(first_name="New name")

        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert etag != new_response.headers["Etag"]

    def test_modified_user_linked_subject_change_subject_new_etag(
        self, user_client, user, subject, memory_store_client_mock
    ) -> None:
        linked_subject = subject
        url = reverse("accounts:user", kwargs={"id": str(user.id)})
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        etag = response.headers["ETag"]

        linked_subject.linked_user = user
        linked_subject.save()

        new_response = user_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert new_response.status_code == status.HTTP_200_OK
        assert etag != new_response.headers["Etag"]
        etag = new_response.headers["Etag"]

        linked_subject.additional = {"test": "test"}
        linked_subject.save()

        new_response = user_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert new_response.status_code == status.HTTP_200_OK

        assert etag != new_response.headers["Etag"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUserProfilesView:
    def test_get_empty_list_of_profiles_by_user(self, superuser_client, memory_store_client_mock):
        user = superuser_client.user
        url = reverse("accounts:user-profiles", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
        assert "ETag" in response.headers.keys()

    def test_get_user_profiles_not_modified_by_user(self, superuser_client, superuser, user, memory_store_client_mock):
        profile_user = user
        superuser.act_as_profiles.add(profile_user)
        superuser.save()

        url = reverse("accounts:user-profiles", kwargs={"id": str(superuser.id)})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        etag = response.headers["ETag"]

        url = reverse("accounts:user-profiles", kwargs={"id": str(superuser.id)})
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert etag == new_response.headers["Etag"]

    def test_get_user_profiles_modified_by_user(self, superuser_client, superuser, user, memory_store_client_mock):
        profile_user = user

        url = reverse("accounts:user-profiles", kwargs={"id": str(superuser.id)})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        superuser.act_as_profiles.add(profile_user)
        superuser.save()
        etag = response.headers["ETag"]

        url = reverse("accounts:user-profiles", kwargs={"id": str(superuser.id)})
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_200_OK
        assert etag != new_response.headers["Etag"]

    def test_user_profile_linked_subject_change(
        self, superuser_client, superuser, user, subject, memory_store_client_mock
    ):
        profile_user = user
        profile_subject = subject

        superuser.act_as_profiles.add(profile_user)
        superuser.save()

        url = reverse("accounts:user-profiles", kwargs={"id": str(superuser.id)})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        etag = response.headers["ETag"]

        profile_subject.linked_user = profile_user
        profile_subject.save()

        url = reverse("accounts:user-profiles", kwargs={"id": str(superuser.id)})
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_200_OK
        assert etag != new_response.headers["Etag"]
