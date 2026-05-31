from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from utils.tenant.release_toggles import (
    RELEASE_TOGGLES,
    ReleaseToggle,
    UnknownReleaseToggle,
    get_release_toggle,
)


def _patch_release_toggles(release_toggles):
    settings = SimpleNamespace(release_toggles=release_toggles)
    return patch("utils.tenant.release_toggles.get_tenant_settings", return_value=settings)


class TestGetReleaseToggle:
    def test_returns_value_from_release_toggles_when_present(self):
        with _patch_release_toggles({"community_input_admin_enabled": True}):
            assert get_release_toggle("community_input_admin_enabled") is True

    def test_returns_registered_default_when_release_toggles_missing_key(self):
        with _patch_release_toggles({}):
            assert get_release_toggle("community_input_admin_enabled") is False

    def test_returns_registered_default_when_release_toggles_is_none(self):
        # Simulate an older Tenant payload that didn't include releaseToggles at all.
        with _patch_release_toggles(None):
            assert get_release_toggle("community_input_admin_enabled") is False

    def test_unknown_toggle_raises(self):
        with _patch_release_toggles({}):
            with pytest.raises(UnknownReleaseToggle):
                get_release_toggle("not_a_real_toggle_name")

    def test_unknown_toggle_raises_even_if_present_in_release_toggles(self):
        # Typo protection: the value being present on the wire is not enough —
        # the code that reads it must declare it in RELEASE_TOGGLES.
        with _patch_release_toggles({"sneaky_undeclared_toggle": True}):
            with pytest.raises(UnknownReleaseToggle):
                get_release_toggle("sneaky_undeclared_toggle")


def _register_toggle(name, toggle):
    """Temporarily add/replace an entry in RELEASE_TOGGLES for a test."""
    return patch.dict(RELEASE_TOGGLES, {name: toggle})


class TestGlobalOverride:
    def test_override_true_wins_over_tenant_value_off(self):
        with _register_toggle("gated", ReleaseToggle(default=False, global_override=True)):
            with _patch_release_toggles({"gated": False}):
                assert get_release_toggle("gated") is True

    def test_override_false_wins_over_tenant_value_on(self):
        with _register_toggle("gated", ReleaseToggle(default=True, global_override=False)):
            with _patch_release_toggles({"gated": True}):
                assert get_release_toggle("gated") is False

    def test_override_none_defers_to_tenant_value(self):
        with _register_toggle("gated", ReleaseToggle(default=False, global_override=None)):
            with _patch_release_toggles({"gated": True}):
                assert get_release_toggle("gated") is True

    def test_override_none_falls_back_to_default(self):
        with _register_toggle("gated", ReleaseToggle(default=True, global_override=None)):
            with _patch_release_toggles({}):
                assert get_release_toggle("gated") is True


class TestRegistry:
    def test_community_input_admin_enabled_is_registered(self):
        toggle = RELEASE_TOGGLES["community_input_admin_enabled"]
        assert isinstance(toggle, ReleaseToggle)
        assert toggle.default is False
        assert toggle.description

    def test_community_input_admin_enabled_has_no_global_override_by_default(self):
        # Ships off for everyone; flip global_override to True to make public.
        assert RELEASE_TOGGLES["community_input_admin_enabled"].global_override is None
