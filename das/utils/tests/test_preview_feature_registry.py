from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from utils.tenant.preview_features import (
    PREVIEW_FEATURES,
    PreviewFeature,
    UnknownPreviewFeature,
    get_preview_feature,
)


def _patch_preview_features(preview_features):
    settings = SimpleNamespace(preview_features=preview_features)
    return patch("utils.tenant.preview_features.get_tenant_settings", return_value=settings)


class TestGetPreviewFeature:
    def test_returns_value_from_preview_features_when_present(self):
        with _patch_preview_features({"community_input_admin_enabled": True}):
            assert get_preview_feature("community_input_admin_enabled") is True

    def test_returns_registered_default_when_preview_features_missing_key(self):
        with _patch_preview_features({}):
            assert get_preview_feature("community_input_admin_enabled") is False

    def test_returns_registered_default_when_preview_features_is_none(self):
        # Simulate an older Tenant payload that didn't include previewFeatures at all.
        with _patch_preview_features(None):
            assert get_preview_feature("community_input_admin_enabled") is False

    def test_unknown_feature_raises(self):
        with _patch_preview_features({}):
            with pytest.raises(UnknownPreviewFeature):
                get_preview_feature("not_a_real_feature_name")

    def test_unknown_feature_raises_even_if_present_in_preview_features(self):
        # Typo protection: the value being present on the wire is not enough —
        # the code that reads it must declare it in PREVIEW_FEATURES.
        with _patch_preview_features({"sneaky_undeclared_feature": True}):
            with pytest.raises(UnknownPreviewFeature):
                get_preview_feature("sneaky_undeclared_feature")


def _register_feature(name, feature):
    """Temporarily add/replace an entry in PREVIEW_FEATURES for a test."""
    return patch.dict(PREVIEW_FEATURES, {name: feature})


class TestGlobalOverride:
    def test_override_true_wins_over_tenant_value_off(self):
        with _register_feature("gated", PreviewFeature(default=False, global_override=True)):
            with _patch_preview_features({"gated": False}):
                assert get_preview_feature("gated") is True

    def test_override_false_wins_over_tenant_value_on(self):
        with _register_feature("gated", PreviewFeature(default=True, global_override=False)):
            with _patch_preview_features({"gated": True}):
                assert get_preview_feature("gated") is False

    def test_override_none_defers_to_tenant_value(self):
        with _register_feature("gated", PreviewFeature(default=False, global_override=None)):
            with _patch_preview_features({"gated": True}):
                assert get_preview_feature("gated") is True

    def test_override_none_falls_back_to_default(self):
        with _register_feature("gated", PreviewFeature(default=True, global_override=None)):
            with _patch_preview_features({}):
                assert get_preview_feature("gated") is True


class TestRegistry:
    def test_community_input_admin_enabled_is_registered(self):
        feature = PREVIEW_FEATURES["community_input_admin_enabled"]
        assert isinstance(feature, PreviewFeature)
        assert feature.default is False
        assert feature.description

    def test_community_input_admin_enabled_has_no_global_override_by_default(self):
        # Ships off for everyone; flip global_override to True to make public.
        assert PREVIEW_FEATURES["community_input_admin_enabled"].global_override is None
