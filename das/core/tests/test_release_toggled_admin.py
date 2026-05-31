from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from django.contrib.admin import ModelAdmin

from core.common import ReleaseToggledAdminMixin


class _FakeAdmin(ReleaseToggledAdminMixin, ModelAdmin):
    release_toggle = "community_input_admin_enabled"


def _make_admin() -> _FakeAdmin:
    admin = _FakeAdmin.__new__(_FakeAdmin)
    admin.opts = SimpleNamespace(app_label="activity")
    return admin


def _patch_tenant_release_toggles(release_toggles):
    """Patch get_tenant_settings inside the registry module so the mixin sees these toggles."""
    settings = SimpleNamespace(release_toggles=release_toggles)
    return patch("utils.tenant.release_toggles.get_tenant_settings", return_value=settings)


class TestReleaseToggledAdminMixin:
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
    def test_returns_false_when_toggle_off(self, method, extra_args):
        admin = _make_admin()
        request = MagicMock()
        with _patch_tenant_release_toggles({"community_input_admin_enabled": False}):
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
    def test_returns_false_when_toggle_absent_from_release_toggles(self, method, extra_args):
        admin = _make_admin()
        request = MagicMock()
        with _patch_tenant_release_toggles({}):
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
    def test_defers_to_super_when_toggle_on(self, method, extra_args):
        admin = _make_admin()
        request = MagicMock()
        with (
            _patch_tenant_release_toggles({"community_input_admin_enabled": True}),
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
    def test_respects_super_denial_when_toggle_on(self, method, extra_args):
        admin = _make_admin()
        request = MagicMock()
        with (
            _patch_tenant_release_toggles({"community_input_admin_enabled": True}),
            patch.object(ModelAdmin, method, return_value=False),
        ):
            assert getattr(admin, method)(request, *extra_args) is False

    def test_empty_release_toggle_attribute_denies(self):
        class _NoToggleAdmin(ReleaseToggledAdminMixin, ModelAdmin):
            pass

        admin = _NoToggleAdmin.__new__(_NoToggleAdmin)
        admin.opts = SimpleNamespace(app_label="activity")
        with _patch_tenant_release_toggles({"community_input_admin_enabled": True}):
            assert admin.has_module_permission(MagicMock()) is False
