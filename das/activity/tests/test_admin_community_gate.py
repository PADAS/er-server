from __future__ import annotations

from unittest.mock import patch

import django.contrib.auth
from django.contrib import admin as django_admin
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from activity.admin import CommunityInputAdmin
from activity.models import CommunityInput
from core.tests import BaseAPITest
from utils.tenant.preview_features import PREVIEW_FEATURES, PreviewFeature

User = django.contrib.auth.get_user_model()


def _without_global_override():
    """Re-register the gating feature with no global_override.

    ``community_input_admin_enabled`` ships with ``global_override=True``, which
    short-circuits the per-tenant lookup. The per-tenant on/off tests below clear
    the override so the value in ``previewFeatures`` is what decides.
    """
    return patch.dict(
        PREVIEW_FEATURES,
        {"community_input_admin_enabled": PreviewFeature(default=False, global_override=None)},
    )


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
        # The admin is gated solely by the per-tenant preview feature at request
        # time (no import-time AdminFeatureFlag kill switch), so the model is
        # always registered; visibility is decided by has_*_permission below.
        assert CommunityInput in django_admin.site._registry

    def test_module_permission_denied_when_feature_off(self):
        self.tenant_settings.preview_features["community_input_admin_enabled"] = False
        with _without_global_override():
            assert self.admin.has_module_permission(self.request) is False
            assert self.admin.has_view_permission(self.request) is False
            assert self.admin.has_add_permission(self.request) is False
            assert self.admin.has_change_permission(self.request) is False
            assert self.admin.has_delete_permission(self.request) is False

    def test_permissions_allowed_when_feature_on(self):
        self.tenant_settings.preview_features["community_input_admin_enabled"] = True
        with _without_global_override():
            assert self.admin.has_module_permission(self.request) is True
            assert self.admin.has_view_permission(self.request) is True
            assert self.admin.has_add_permission(self.request) is True
            assert self.admin.has_change_permission(self.request) is True
            assert self.admin.has_delete_permission(self.request) is True

    def test_global_override_on_exposes_admin_despite_feature_off(self):
        # "Make it public for everyone": global_override=True wins over a tenant
        # that has the feature off in previewFeatures.
        self.tenant_settings.preview_features["community_input_admin_enabled"] = False
        with patch.dict(
            PREVIEW_FEATURES,
            {"community_input_admin_enabled": PreviewFeature(default=False, global_override=True)},
        ):
            assert self.admin.has_module_permission(self.request) is True
            assert self.admin.has_view_permission(self.request) is True

    def test_global_override_off_hides_admin_despite_feature_on(self):
        # Emergency kill: global_override=False wins over a tenant that opted in.
        self.tenant_settings.preview_features["community_input_admin_enabled"] = True
        with patch.dict(
            PREVIEW_FEATURES,
            {"community_input_admin_enabled": PreviewFeature(default=False, global_override=False)},
        ):
            assert self.admin.has_module_permission(self.request) is False
            assert self.admin.has_view_permission(self.request) is False
