from copy import deepcopy
from unittest.mock import MagicMock, patch

import django_multitenant.utils
import pytest

import django.contrib.auth
from django.urls import reverse

import utils.tenant.thread
from accounts.views import UserView
from activity.models import EventCategory, EventType
from activity.views import EventCategoriesView, EventCategoryView
from core.tests import BaseAPITest

User = django.contrib.auth.get_user_model()


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class test_retrieve_event_category_with_event_types(BaseAPITest):
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
