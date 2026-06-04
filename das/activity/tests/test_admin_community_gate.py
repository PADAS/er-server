from __future__ import annotations

from unittest.mock import patch

import django.contrib.auth
from django.contrib import admin as django_admin
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from activity.admin import CommunityInputAdmin
from activity.models import CommunityInput
from core.tests import BaseAPITest
from utils.tenant.release_toggles import RELEASE_TOGGLES, ReleaseToggle

User = django.contrib.auth.get_user_model()


class TestCommunityInputAdminGate(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_user(
            "ci-admin",
            "ci-admin@test.com",
            "ci-admin",
            is_superuser=True,
            is_staff=True,
            last_name="last",
            first_name="first",
        )
        self.admin = CommunityInputAdmin(model=CommunityInput, admin_site=AdminSite())
        self.request = RequestFactory().get("/admin/activity/communityinput/")
        self.request.user = self.superuser

    def test_admin_is_always_registered(self):
        # The admin is gated solely by the per-tenant release toggle at request
        # time (no import-time AdminFeatureFlag kill switch), so the model is
        # always registered; visibility is decided by has_*_permission below.
        assert CommunityInput in django_admin.site._registry

    def test_module_permission_denied_when_toggle_off(self):
        self.tenant_settings.release_toggles["community_input_admin_enabled"] = False
        assert self.admin.has_module_permission(self.request) is False
        assert self.admin.has_view_permission(self.request) is False
        assert self.admin.has_add_permission(self.request) is False
        assert self.admin.has_change_permission(self.request) is False
        assert self.admin.has_delete_permission(self.request) is False

    def test_permissions_allowed_when_toggle_on(self):
        self.tenant_settings.release_toggles["community_input_admin_enabled"] = True
        assert self.admin.has_module_permission(self.request) is True
        assert self.admin.has_view_permission(self.request) is True
        assert self.admin.has_add_permission(self.request) is True
        assert self.admin.has_change_permission(self.request) is True
        assert self.admin.has_delete_permission(self.request) is True

    def test_global_override_on_exposes_admin_despite_toggle_off(self):
        # "Make it public for everyone": global_override=True wins over a tenant
        # that has the toggle off in releaseToggles.
        self.tenant_settings.release_toggles["community_input_admin_enabled"] = False
        with patch.dict(
            RELEASE_TOGGLES,
            {"community_input_admin_enabled": ReleaseToggle(default=False, global_override=True)},
        ):
            assert self.admin.has_module_permission(self.request) is True
            assert self.admin.has_view_permission(self.request) is True

    def test_global_override_off_hides_admin_despite_toggle_on(self):
        # Emergency kill: global_override=False wins over a tenant that opted in.
        self.tenant_settings.release_toggles["community_input_admin_enabled"] = True
        with patch.dict(
            RELEASE_TOGGLES,
            {"community_input_admin_enabled": ReleaseToggle(default=False, global_override=False)},
        ):
            assert self.admin.has_module_permission(self.request) is False
            assert self.admin.has_view_permission(self.request) is False
