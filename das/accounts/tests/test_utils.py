import pytest

from rest_framework.exceptions import PermissionDenied

from accounts.utils import (
    fetch_organization_choices,
    fetch_tech_choices,
    get_profile_user,
    get_profiles,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestUtils:
    def test_fetch_tech_choices(self, five_choices):
        five_choices[0].field = "tech"
        five_choices[0].save()
        five_choices[1].field = "tech"
        five_choices[1].save()

        tech_choices = fetch_tech_choices()

        assert tech_choices == (("value_0", "display_0"), ("value_1", "display_1"))

    def test_fetch_empty_tech_choices(self):
        tech_choices = fetch_tech_choices()

        assert tech_choices == ()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestFetchOrganizationChoices:
    def test_fetch_organization_choices(self, five_choices):
        five_choices[0].field = "organization"
        five_choices[0].save()
        five_choices[1].field = "organization"
        five_choices[1].save()

        tech_choices = fetch_organization_choices()

        assert tech_choices == (
            ("", ""),
            (five_choices[0].value, five_choices[0].display),
            (five_choices[1].value, five_choices[1].display),
        )

    def test_fetch_empty_organization_choices(self):
        tech_choices = fetch_organization_choices()

        assert tech_choices == (("", ""),)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGetProfiles:
    def test_without_children(self, five_users):
        user = five_users[0]
        users = set([user.id for user in get_profiles([user.id])])

        assert {five_users[1].id, five_users[2].id, five_users[3].id, five_users[4].id} == users
        assert user.username not in users

    def test_with_children(self, five_users):
        father = five_users[0]
        father.act_as_profiles.add(five_users[0])

        users = set([user.id for user in get_profiles([father.id])])

        assert {five_users[1].id, five_users[2].id, five_users[3].id, five_users[4].id} == users
        assert father.username not in users

    def test_get_profile_user_permission_denied_when_user_is_not_in_profiles(self, five_users):
        father = five_users[0]
        father.act_as_profiles.add(five_users[1])
        not_profile_user_id = five_users[2].id
        with pytest.raises(PermissionDenied):
            profile_user = get_profile_user(father.id, not_profile_user_id)
            assert profile_user is None

    def test_get_profile_user(self, five_users):
        user = five_users[0]
        profile_user = five_users[1]
        user.act_as_profiles.add(profile_user)

        assert profile_user.id == get_profile_user(user.id, profile_user.id).id
