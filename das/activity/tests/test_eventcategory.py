from copy import deepcopy
from unittest.mock import MagicMock, patch

import django_multitenant.utils
import pytest

import django.contrib.auth
from django.urls import reverse
from rest_framework import status

import utils.tenant.thread
from accounts.models.permissionset import PermissionSet
from accounts.views import UserView
from activity.models import EventCategory, EventType
from activity.views import EventCategoriesView, EventCategoryView
from core.tests import BaseAPITest
from utils.rank import RankedTool

User = django.contrib.auth.get_user_model()


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRetrieveEventCategoryWithEventTypes(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.event_category_url = reverse("admin:activity_eventcategory_changelist")
        user_const = dict(last_name="last", first_name="first")
        self.user = User.objects.create_user(
            "user", "user@test.com", "all_perms_user", is_superuser=True, is_staff=True, **user_const
        )
        self.no_perms_user = User.objects.create_user(
            "no_perms_user", "das_no_perms@vulcan.com", "noperms", **user_const
        )
        EventCategory.objects.create(value="security", display="Security", ordernum=1)
        self.event_category_logistic = EventCategory.objects.create(value="logistic", display="Logistic", ordernum=1)

    def test_no_event_categories_display(self):
        # User with no-perms can't view event categories.
        request = self.factory.get(self.event_category_url)
        self.force_authenticate(request, self.no_perms_user)
        response = EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_view_event_categories_with_perms(self):
        request = self.factory.get(self.event_category_url)
        self.force_authenticate(request, self.user)
        response = EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)

    @pytest.mark.usefixtures("tenant_response_for_test_case")
    @patch("accounts.serializers.get_tenant_settings")
    def test_create_event_category_with_restricted_character(self, get_tenant_settings):
        get_tenant_settings.return_value = deepcopy(self.tenant_response)

        EventCategory.objects.create(value=".", display="Testing", ordernum=1)

        url = "api/v1.0/user/me"
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = UserView.as_view()(request, id=self.user.id)
        self.assertEqual(response.status_code, 200)

    @pytest.mark.usefixtures("tenant_two")
    def test_superuser_does_not_see_permissions_from_other_tenant(self):
        thread_locals = MagicMock()
        thread_locals.tenant = self.tenant_two_object
        with patch.object(django_multitenant.utils, "_thread_locals", thread_locals):
            thread = MagicMock()
            thread.tenant_object = self.tenant_two_settings
            with patch.object(utils.tenant.thread, "_local_thread", thread):
                EventCategory.objects.create(value="superuser_test", display="Testing", ordernum=1)

        url = "api/v1.0/user/me"
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = UserView.as_view()(request, id=self.user.id)
        self.assertEqual(response.status_code, 200)

        assert "superuser_test" not in response.data["permissions"].keys()

    def test_create_event_categories_perms(self):
        # add new event-category (user with event-category permission)
        url = reverse("event-categories")
        data = {"value": "ec_value", "display": "ec_display", "flag": "user"}
        request = self.factory.post(url, data=data)
        self.force_authenticate(request, self.user)
        response = EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data)

        # user with no event-category permission should not be able to add new event-category.
        request = self.factory.post(url, data=data)
        self.force_authenticate(request, self.no_perms_user)
        response = EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_create_event_categories_without_ordernum(self):
        url = reverse("event-categories")
        data = {"value": "ec_value", "display": "ec_display", "flag": "user"}
        request = self.factory.post(url, data=data)
        self.force_authenticate(request, self.user)

        response = EventCategoriesView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["ordernum"], 0.5)

    def test_retrieve_event_category(self):
        eventcategory_id = str(EventCategory.objects.first().id)
        url = reverse("event-category", kwargs={"eventcategory_id": eventcategory_id})
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = EventCategoryView.as_view()(request, eventcategory_id=eventcategory_id)
        self.assertEqual(response.status_code, 200)

    def test_retrieve_event_category_with_event_types(self):
        obj = EventCategory.objects.create(value="test_event_category", display="test_event_category", ordernum=1)
        EventType.objects.create(value="event_type", display="Event Type", category=obj)
        url = reverse("event-category", kwargs={"eventcategory_id": obj.id})
        request = self.factory.get(url, {"include_event_types": "true"})
        self.force_authenticate(request, self.user)

        response = EventCategoryView.as_view()(request, eventcategory_id=obj.id)

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            {
                "display",
                "geometry_type",
                "icon",
                "id",
                "is_active",
                "ordernum",
                "value",
            }
            <= response.data.get("event_types")[0].keys()
        )

    def test_retrieve_event_categories_with_event_types(self):
        obj = EventCategory.objects.create(value="test_event_category", display="test_event_category", ordernum=1)
        EventType.objects.create(value="event_type", display="Event Type", category=obj)
        url = reverse("event-categories")
        request = self.factory.get(f"{url}?include_event_types=true")
        self.force_authenticate(request, self.user)

        response = EventCategoriesView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            {
                "display",
                "geometry_type",
                "icon",
                "id",
                "is_active",
                "ordernum",
                "value",
            }
            <= response.data[0].get("event_types")[0].keys()
        )

    def test_patch_event_category(self):
        eventcategory_id = str(EventCategory.objects.first().id)
        url = reverse("event-category", kwargs={"eventcategory_id": eventcategory_id})
        data = {"value": "new-value"}
        request = self.factory.patch(url, data)
        self.force_authenticate(request, self.user)
        response = EventCategoryView.as_view()(request, eventcategory_id=eventcategory_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("value"), data.get("value"))

    def test_delete_event_category(self):
        eventcategory_id = str(self.event_category_logistic.id)
        url = reverse("event-category", kwargs={"eventcategory_id": eventcategory_id})
        request = self.factory.delete(url)
        self.force_authenticate(request, self.user)
        response = EventCategoryView.as_view()(request, eventcategory_id=eventcategory_id)
        response.render()
        self.assertEqual(response.status_code, 200)

    def test_delete_event_category_with_eventtypes(self):
        eventcategory_id = str(self.event_category_logistic.id)
        EventType.objects.create(value="event_type", display="Event Type", category_id=eventcategory_id)
        url = reverse("event-category", kwargs={"eventcategory_id": eventcategory_id})

        request = self.factory.delete(url)
        self.force_authenticate(request, self.user)
        response = EventCategoryView.as_view()(request, eventcategory_id=eventcategory_id)
        response.render()

        self.assertEqual(response.status_code, 400)

    def test_retrieve_event_categories_with_include_permission_set_changed(self):
        url = reverse("event-categories")

        request = self.factory.get(f"{url}?include_permission_set_changed=true")
        self.user.is_superuser = True
        self.user.save()
        self.force_authenticate(request, self.user)

        response = EventCategoriesView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        self.assertTrue("permission_set_changed" in response.data[0].keys())


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db
class TestEventCategoryUpdatePermissions:
    def test_update_event_category_permissions_silently(self, five_event_categories, superuser_client):
        event_category = five_event_categories[1]
        new_value = f"{event_category.value}_changed"
        new_display = f"{event_category.display}_changed"

        url = reverse("event-category", kwargs={"eventcategory_id": event_category.id})
        data = {"value": new_value, "display": new_display}
        response = superuser_client.patch(url, data=data)

        event_category.refresh_from_db()
        base_qs = PermissionSet.objects.prefetch_related("permissions").all()

        assert response.status_code == status.HTTP_200_OK
        assert base_qs.get(name=event_category.auto_permissionset_name)
        assert base_qs.get(name=event_category.auto_geographic_permission_set_name)

    def test_update_event_category_permissions_changed_but_updated_explitclty(
        self, five_event_categories, superuser_client
    ):
        event_category = five_event_categories[1]
        new_value = f"{event_category.value}_changed"

        permission_set = PermissionSet.objects.get(name=event_category.auto_permissionset_name)
        permission_set.name = "new_permission_name"
        permission_set.save(update_fields=["name"])

        url = reverse("event-category", kwargs={"eventcategory_id": event_category.id})
        url = f"{url}?update_permission_sets=true"

        data = {"value": new_value}
        response = superuser_client.patch(url, data=data)

        event_category.refresh_from_db()

        permission_set = PermissionSet.objects.get(name="new_permission_name")
        geo_permission_set = PermissionSet.objects.get(name=event_category.auto_geographic_permission_set_name)

        assert response.status_code == status.HTTP_200_OK
        assert event_category.auto_permissionset_name != permission_set.name
        assert event_category.auto_geographic_permission_set_name == geo_permission_set.name


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.django_db
class TestEventCategories:
    def test_event_categories_should_have_etag(self, superuser_client):
        url = reverse("event-categories")
        response = superuser_client.get(url)
        etag = response["eTag"]

        response = superuser_client.get(url, HTTP_IF_NONE_MATCH=etag)
        assert response.status_code == status.HTTP_304_NOT_MODIFIED

    def test_etag_should_change_when_event_category_is_updated(self, superuser_client):
        url = reverse("event-categories")
        response = superuser_client.get(url)
        initial_etag = response["eTag"]

        event_category = EventCategory.objects.first()
        event_category.ordernum = 123.123
        event_category.save(update_fields=["ordernum"])

        response = superuser_client.get(url, HTTP_IF_NONE_MATCH=initial_etag)
        assert response.status_code == status.HTTP_200_OK

        new_etag = response["eTag"]
        assert new_etag != initial_etag


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestEventCategoryGeoPermissionVisibility:
    """Regression coverage for ERA-11577.

    A user holding only the geographic permission set for a category must still
    see that category in the list and detail endpoints, exactly as the
    ``/eventtypes`` endpoints already allow. Before the fix the categories list
    only consulted the four general action codenames, so a geo-only user was
    excluded from every category.
    """

    @pytest.mark.parametrize("version", [EventType.VersionChoices.VERSION_1, EventType.VersionChoices.VERSION_2])
    def test_geo_only_user_sees_category_in_list(self, version, create_user, create_client_for_user):
        category = EventCategory.objects.create(value="geo_only", display="Geo Only", ordernum=1)
        EventType.objects.create(value="geo_only_type", display="Geo Only Type", category=category, version=version)

        user = create_user()
        geo_permission_set = PermissionSet.objects.get(name=category.auto_geographic_permission_set_name)
        user.permission_sets.add(geo_permission_set)
        client = create_client_for_user(user)

        response = client.get(reverse("event-categories"))

        assert response.status_code == status.HTTP_200_OK
        returned_values = {item["value"] for item in response.data}
        assert category.value in returned_values

    def test_geo_only_user_gets_200_on_category_detail(self, create_user, create_client_for_user):
        category = EventCategory.objects.create(value="geo_only_detail", display="Geo Only Detail", ordernum=1)

        user = create_user()
        geo_permission_set = PermissionSet.objects.get(name=category.auto_geographic_permission_set_name)
        user.permission_sets.add(geo_permission_set)
        client = create_client_for_user(user)

        url = reverse("event-category", kwargs={"eventcategory_id": str(category.id)})
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] == category.value

    def test_user_with_only_non_view_geo_permission_gets_200_on_category_detail(
        self, create_user, create_client_for_user
    ):
        # Comment-1 regression: previously the detail endpoint only consulted the
        # single geo verb mapped from GET ("view"), so a user holding only a
        # non-view geo permission (e.g. "add") got 403 on detail even though the
        # list endpoint showed the category. Detail must now mirror list and
        # grant on ANY general or geographic category permission.
        category = EventCategory.objects.create(value="geo_add_only", display="Geo Add Only", ordernum=1)

        geo_permission_set = PermissionSet.objects.get(name=category.auto_geographic_permission_set_name)
        add_geo_permission = geo_permission_set.permissions.get(codename__contains=f"add_{category.value}_gd")

        add_only_permission_set = PermissionSet.objects.create(name=f"{category.value}_add_geo_only")
        add_only_permission_set.permissions.add(add_geo_permission)

        user = create_user()
        user.permission_sets.add(add_only_permission_set)
        client = create_client_for_user(user)

        url = reverse("event-category", kwargs={"eventcategory_id": str(category.id)})
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["value"] == category.value

    def test_user_without_general_or_geo_permission_does_not_see_category(self, create_user, create_client_for_user):
        category = EventCategory.objects.create(value="no_perms_cat", display="No Perms Cat", ordernum=1)

        user = create_user()
        client = create_client_for_user(user)

        list_response = client.get(reverse("event-categories"))
        assert list_response.status_code == status.HTTP_200_OK
        returned_values = {item["value"] for item in list_response.data}
        assert category.value not in returned_values

        detail_url = reverse("event-category", kwargs={"eventcategory_id": str(category.id)})
        detail_response = client.get(detail_url)
        assert detail_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestEventCategoryRanking:

    def test_rank_second_as_first(self, superuser_client, five_event_categories):
        qs = EventCategory.objects.all().order_by("ordernum", "value")
        RankedTool.make_full_rebalance(queryset=qs)
        event_category = list(qs)[1]

        url = reverse("event-category-ranking", kwargs={"eventcategory_id": str(event_category.id)})

        response = superuser_client.post(url, {"before_key": None})
        assert response.status_code == status.HTTP_200_OK
        obj = EventCategory.objects.get(id=event_category.id)
        assert obj.ordernum == 0.5

        response = superuser_client.post(url, {"before_key": ""})
        assert response.status_code == status.HTTP_200_OK
        obj = EventCategory.objects.get(id=event_category.id)
        assert obj.ordernum == 0.5

        response = superuser_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        obj = EventCategory.objects.get(id=event_category.id)
        assert obj.ordernum == 0.5

    def test_event_category_ranking_first_stays_first_with_before_none(self, superuser_client, five_event_categories):
        qs = EventCategory.objects.all().order_by("ordernum", "value")
        RankedTool.make_full_rebalance(queryset=qs)
        first_category = list(qs)[0]
        orig_ordernum = first_category.ordernum

        url = reverse("event-category-ranking", kwargs={"eventcategory_id": str(first_category.id)})
        response = superuser_client.post(url, {"before_key": None})
        assert response.status_code == status.HTTP_200_OK

        obj = EventCategory.objects.get(id=first_category.id)
        assert obj.ordernum == orig_ordernum
