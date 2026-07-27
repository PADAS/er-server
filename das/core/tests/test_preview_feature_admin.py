from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from django.contrib.admin import ModelAdmin

from core.common import PreviewFeatureAdminMixin
from utils.tenant.preview_features import PREVIEW_FEATURES, PreviewFeature


class _FakeAdmin(PreviewFeatureAdminMixin, ModelAdmin):
    preview_feature = "community_input_admin_enabled"


def _make_admin() -> _FakeAdmin:
    admin = _FakeAdmin.__new__(_FakeAdmin)
    admin.opts = SimpleNamespace(app_label="activity")
    return admin


def _patch_tenant_preview_features(preview_features):
    """Patch get_tenant_settings inside the registry module so the mixin sees these features."""
    settings = SimpleNamespace(preview_features=preview_features)
    return patch("utils.tenant.preview_features.get_tenant_settings", return_value=settings)


def _without_global_override():
    """Re-register the gating feature with no global_override.

    ``community_input_admin_enabled`` ships with ``global_override=True``, which
    short-circuits the per-tenant lookup. These tests are about the mixin's
    behaviour for a given *per-tenant* value, so the override is cleared to let
    the tenant value reach the mixin.
    """
    return patch.dict(
        PREVIEW_FEATURES,
        {"community_input_admin_enabled": PreviewFeature(default=False, global_override=None)},
    )


class TestPreviewFeatureAdminMixin:
    @pytest.mark.parametrize(
        "method,extra_args",
        [
            ("has_module_permission", ()),
            ("has_view_permission", (None,)),
            ("has_add_permission", ()),
            ("has_change_permission", (None,)),
            ("has_delete_permission", (None,)),
        ],
    )
    def test_returns_false_when_feature_off(self, method, extra_args):
        admin = _make_admin()
        request = MagicMock()
        with (
            _without_global_override(),
            _patch_tenant_preview_features({"community_input_admin_enabled": False}),
        ):
            assert getattr(admin, method)(request, *extra_args) is False

    @pytest.mark.parametrize(
        "method,extra_args",
        [
            ("has_module_permission", ()),
            ("has_view_permission", (None,)),
            ("has_add_permission", ()),
            ("has_change_permission", (None,)),
            ("has_delete_permission", (None,)),
        ],
    )
    def test_returns_false_when_feature_absent_from_preview_features(self, method, extra_args):
        admin = _make_admin()
        request = MagicMock()
        with (
            _without_global_override(),
            _patch_tenant_preview_features({}),
        ):
            assert getattr(admin, method)(request, *extra_args) is False

    @pytest.mark.parametrize(
        "method,extra_args",
        [
            ("has_module_permission", ()),
            ("has_view_permission", (None,)),
            ("has_add_permission", ()),
            ("has_change_permission", (None,)),
            ("has_delete_permission", (None,)),
        ],
    )
    def test_defers_to_super_when_feature_on(self, method, extra_args):
        admin = _make_admin()
        request = MagicMock()
        with (
            _without_global_override(),
            _patch_tenant_preview_features({"community_input_admin_enabled": True}),
            patch.object(ModelAdmin, method, return_value=True) as super_method,
        ):
            assert getattr(admin, method)(request, *extra_args) is True
            super_method.assert_called_once()

    @pytest.mark.parametrize(
        "method,extra_args",
        [
            ("has_module_permission", ()),
            ("has_view_permission", (None,)),
            ("has_add_permission", ()),
            ("has_change_permission", (None,)),
            ("has_delete_permission", (None,)),
        ],
    )
    def test_respects_super_denial_when_feature_on(self, method, extra_args):
        admin = _make_admin()
        request = MagicMock()
        with (
            _without_global_override(),
            _patch_tenant_preview_features({"community_input_admin_enabled": True}),
            patch.object(ModelAdmin, method, return_value=False),
        ):
            assert getattr(admin, method)(request, *extra_args) is False

    def test_empty_preview_feature_attribute_denies(self):
        class _NoFeatureAdmin(PreviewFeatureAdminMixin, ModelAdmin):
            pass

        admin = _NoFeatureAdmin.__new__(_NoFeatureAdmin)
        admin.opts = SimpleNamespace(app_label="activity")
        with _patch_tenant_preview_features({"community_input_admin_enabled": True}):
            assert admin.has_module_permission(MagicMock()) is False
