import pytest

from django.urls import reverse
from rest_framework import status

from accounts.models import User


@pytest.fixture
def five_inactive_users():
    return User.objects.bulk_create(
        [
            User(username="user1", password="password", is_active=False),
            User(username="user2", password="password", is_active=False),
            User(username="user3", password="password", is_active=False),
            User(username="user4", password="password", is_active=False),
            User(username="user5", password="password", is_active=False),
        ]
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUsersListView:
    def test_get_list_of_users(self, superuser_client):
        url = reverse("accounts:users")
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_get_list_of_users_include_inactive(self, superuser_client, five_inactive_users):
        url = reverse("accounts:users")
        active_users_count = User.objects.filter(is_active=True).count()
        inactive_users_count = User.objects.filter(is_active=False).count()

        assert active_users_count > 0
        assert inactive_users_count > 0

        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == active_users_count
        response_head = superuser_client.head(url)
        assert response_head.status_code == status.HTTP_200_OK

        response = superuser_client.get(url, {"include_inactive": "false"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == active_users_count
        response_head = superuser_client.head(url, {"include_inactive": "false"})
        assert response_head.status_code == status.HTTP_200_OK

        response = superuser_client.get(url, {"include_inactive": "true"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == active_users_count + inactive_users_count
        response_head = superuser_client.head(url, {"include_inactive": "true"})
        assert response_head.status_code == status.HTTP_200_OK


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUserView:
    def test_get_user(self, superuser_client):
        user = superuser_client.user
        url = reverse("accounts:user", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()

    def test_get_user_no_modified(self, superuser_client):
        user = superuser_client.user
        url = reverse("accounts:user", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()

        etag = response.headers["ETag"]
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert etag == new_response.headers["ETag"]

    def test_get_user_no_modified_profile_user(self, superuser_client, user):
        url = reverse("accounts:user", kwargs={"id": str(user.id)})
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "ETag" in response.headers.keys()

        etag = response.headers["ETag"]

        superuser_client.credentials(USER_PROFILE=user)
        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)

        assert new_response.status_code == status.HTTP_304_NOT_MODIFIED
        assert etag == new_response.headers["ETag"]

    def test_get_inactive_user(self, superuser_client, five_inactive_users):
        url = reverse("accounts:user", kwargs={"id": str(five_inactive_users[0].id)})

        response = superuser_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        response_head = superuser_client.head(url)
        assert response_head.status_code == status.HTTP_404_NOT_FOUND

        response = superuser_client.get(url, {"include_inactive": "true"})
        assert response.status_code == status.HTTP_200_OK
        response_head = superuser_client.head(url, {"include_inactive": "true"})
        assert response_head.status_code == status.HTTP_200_OK

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

    def test_modified_user_new_etag(self, superuser_client) -> None:
        user = superuser_client.user
        url = reverse("accounts:user", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)
        etag = response.headers["ETag"]

        User.objects.filter(id=user.id).update(first_name="New name")

        new_response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert etag != new_response.headers["Etag"]

    def test_modified_user_linked_subject_change_subject_new_etag(self, user_client, user, subject) -> None:
        linked_subject = subject
        url = reverse("accounts:user", kwargs={"id": str(user.id)})
        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        etag = response.headers["ETag"]

        linked_subject.linked_user = user
        linked_subject.save()

        new_response = user_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert new_response.status_code == status.HTTP_200_OK
        assert etag != new_response.headers["ETag"]
        etag = new_response.headers["ETag"]

        linked_subject.additional = {"test": "test"}
        linked_subject.save()

        new_response = user_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert new_response.status_code == status.HTTP_200_OK

        assert etag != new_response.headers["ETag"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUserProfilesView:
    def test_get_empty_list_of_profiles_by_user(self, superuser_client):
        user = superuser_client.user
        url = reverse("accounts:user-profiles", kwargs={"id": str(user.id)})

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
        assert "ETag" in response.headers.keys()

    def test_get_user_profiles_not_modified_by_user(self, superuser_client, superuser, user):
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
        assert etag == new_response.headers["ETag"]

    def test_get_user_profiles_modified_by_user(self, superuser_client, superuser, user):
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
        assert etag != new_response.headers["ETag"]

    def test_user_profile_linked_subject_change(self, superuser_client, superuser, user, subject):
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
        assert etag != new_response.headers["ETag"]

    def test_std_user_with_profile_and_profile_can_retrieve_user_info(self, user_client, five_users):
        profile_user = five_users[0]
        user_client.user.act_as_profiles.add(profile_user)

        url = reverse("accounts:user", kwargs={"id": str(profile_user.id)})
        response = user_client.get(url, HTTP_USER_PROFILE=str(profile_user.id))

        assert response.status_code == status.HTTP_200_OK

    def test_std_user_with_profile_retrieve_by_id_should_return_404(self, user_client, five_users):
        profile_user = five_users[0]
        user_client.user.act_as_profiles.add(profile_user)

        url = reverse("accounts:user", kwargs={"id": str(profile_user.id)})
        response = user_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
