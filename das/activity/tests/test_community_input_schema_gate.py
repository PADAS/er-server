"""Tests for the Community Input schema feature gate.

The ``SC_REVIEW`` event state is part of the Community Input feature and must be
hidden from UI-facing rendered schemas (``events/schema/`` and
``eventfilters/schema/``) unless the per-tenant ``community_input_admin_enabled``
preview feature is enabled.  Input validation (serializer acceptance) must NOT
be affected: the API must continue to accept ``state="review"`` as a valid value
regardless of the feature flag.
"""

from __future__ import annotations

from unittest.mock import patch

import django.contrib.auth
from rest_framework import status
from rest_framework.test import APIRequestFactory

from activity import views
from activity.constants import SC_REVIEW
from activity.models import Event
from activity.serializers.helpers import get_hidden_event_states
from core.tests import BaseAPITest
from utils.tenant.preview_features import PREVIEW_FEATURES, PreviewFeature

User = django.contrib.auth.get_user_model()


def _without_global_override():
    """Re-register the gating feature with no global_override.

    ``community_input_admin_enabled`` ships with ``global_override=True``, which
    short-circuits the per-tenant lookup. The tests below exercise the per-tenant
    gate, so they clear the override to let the ``previewFeatures`` value decide.
    """
    return patch.dict(
        PREVIEW_FEATURES,
        {"community_input_admin_enabled": PreviewFeature(default=False, global_override=None)},
    )


# ---------------------------------------------------------------------------
# Unit tests for get_hidden_event_states()
# ---------------------------------------------------------------------------


class TestGetHiddenEventStates(BaseAPITest):
    """Direct unit tests for the ``get_hidden_event_states`` helper."""

    def test_returns_sc_review_when_feature_is_off(self) -> None:
        self.tenant_settings.preview_features["community_input_admin_enabled"] = False
        with _without_global_override():
            hidden = get_hidden_event_states()
        assert SC_REVIEW in hidden

    def test_returns_empty_set_when_feature_is_on(self) -> None:
        self.tenant_settings.preview_features["community_input_admin_enabled"] = True
        with _without_global_override():
            hidden = get_hidden_event_states()
        assert hidden == set()

    def test_returns_sc_review_when_feature_absent_from_tenant(self) -> None:
        # No explicit value — falls back to the default (False).
        self.tenant_settings.preview_features.pop("community_input_admin_enabled", None)
        with _without_global_override():
            hidden = get_hidden_event_states()
        assert SC_REVIEW in hidden

    def test_global_override_true_returns_empty_set(self) -> None:
        self.tenant_settings.preview_features["community_input_admin_enabled"] = False
        with patch.dict(
            PREVIEW_FEATURES,
            {"community_input_admin_enabled": PreviewFeature(default=False, global_override=True)},
        ):
            hidden = get_hidden_event_states()
        assert hidden == set()

    def test_global_override_false_returns_sc_review_despite_tenant_opt_in(self) -> None:
        self.tenant_settings.preview_features["community_input_admin_enabled"] = True
        with patch.dict(
            PREVIEW_FEATURES,
            {"community_input_admin_enabled": PreviewFeature(default=False, global_override=False)},
        ):
            hidden = get_hidden_event_states()
        assert SC_REVIEW in hidden


# ---------------------------------------------------------------------------
# EventSchemaView tests  (GET activity/events/schema/)
# ---------------------------------------------------------------------------


class TestEventSchemaViewStateGate(BaseAPITest):
    """The ``events/schema/`` endpoint must hide ``SC_REVIEW`` from the state
    field's ``enum`` / ``enum_ext`` when the feature is off."""

    def setUp(self) -> None:
        super().setUp()
        self.superuser = User.objects.create_user(
            "schema-gate-superuser",
            "schema-gate@test.com",
            "schema-gate",
            is_superuser=True,
            is_staff=True,
            last_name="last",
            first_name="first",
        )
        self.factory = APIRequestFactory(enforce_csrf_checks=False)

    def _get_state_field(self, flag_value: bool) -> dict:
        self.tenant_settings.preview_features["community_input_admin_enabled"] = flag_value
        request = self.factory.get("/activity/events/schema/")
        self.force_authenticate(request, self.superuser)
        with _without_global_override():
            response = views.EventSchemaView.as_view()(request)
        assert response.status_code == status.HTTP_200_OK
        return response.data.get("properties", {}).get("state", {})

    def test_review_state_hidden_from_enum_when_feature_off(self) -> None:
        state_field = self._get_state_field(flag_value=False)
        assert "enum" in state_field, "state field should have an enum key"
        assert SC_REVIEW not in state_field["enum"]

    def test_review_state_hidden_from_enum_ext_when_feature_off(self) -> None:
        state_field = self._get_state_field(flag_value=False)
        enum_ext_values = [entry["value"] for entry in state_field.get("enum_ext", [])]
        assert SC_REVIEW not in enum_ext_values

    def test_review_state_present_in_enum_when_feature_on(self) -> None:
        state_field = self._get_state_field(flag_value=True)
        assert "enum" in state_field
        assert SC_REVIEW in state_field["enum"]

    def test_review_state_present_in_enum_ext_when_feature_on(self) -> None:
        state_field = self._get_state_field(flag_value=True)
        enum_ext_values = [entry["value"] for entry in state_field.get("enum_ext", [])]
        assert SC_REVIEW in enum_ext_values

    def test_other_states_always_present_when_feature_off(self) -> None:
        state_field = self._get_state_field(flag_value=False)
        enum_values = state_field.get("enum", [])
        for expected_state in (Event.SC_NEW, Event.SC_ACTIVE, Event.SC_RESOLVED):
            assert expected_state in enum_values, f"state {expected_state!r} should always be visible"

    def test_schema_endpoint_returns_200_regardless_of_flag(self) -> None:
        for flag_value in (True, False):
            # _get_state_field already asserts a 200 response for each flag value.
            assert self._get_state_field(flag_value=flag_value) != {}


# ---------------------------------------------------------------------------
# EventFilterSchemaView tests  (GET activity/eventfilters/schema/)
# ---------------------------------------------------------------------------


class TestEventFilterSchemaViewStateGate(BaseAPITest):
    """The ``eventfilters/schema/`` endpoint must hide ``SC_REVIEW`` from the
    state filter enum when the feature is off."""

    def setUp(self) -> None:
        super().setUp()
        self.superuser = User.objects.create_user(
            "filter-schema-gate-superuser",
            "filter-schema-gate@test.com",
            "filter-schema-gate",
            is_superuser=True,
            is_staff=True,
            last_name="last",
            first_name="first",
        )
        self.factory = APIRequestFactory(enforce_csrf_checks=False)

    def _get_state_enum(self, flag_value: bool) -> list[dict]:
        self.tenant_settings.preview_features["community_input_admin_enabled"] = flag_value
        request = self.factory.get("/activity/eventfilters/schema/")
        self.force_authenticate(request, self.superuser)
        with _without_global_override():
            response = views.EventFilterSchemaView.as_view()(request)
        assert response.status_code == status.HTTP_200_OK
        items = response.data["schema"]["properties"]["state"]["items"]
        return items["enum"]

    def test_review_state_absent_from_state_enum_when_feature_off(self) -> None:
        enum = self._get_state_enum(flag_value=False)
        ids = [entry["id"] for entry in enum]
        assert SC_REVIEW not in ids

    def test_review_state_present_in_state_enum_when_feature_on(self) -> None:
        enum = self._get_state_enum(flag_value=True)
        ids = [entry["id"] for entry in enum]
        assert SC_REVIEW in ids

    def test_other_states_always_in_state_enum_when_feature_off(self) -> None:
        enum = self._get_state_enum(flag_value=False)
        ids = [entry["id"] for entry in enum]
        for expected_state in (Event.SC_NEW, Event.SC_ACTIVE, Event.SC_RESOLVED):
            assert expected_state in ids, f"state {expected_state!r} should always be visible"

    def test_filter_schema_returns_200_regardless_of_flag(self) -> None:
        for flag_value in (True, False):
            enum = self._get_state_enum(flag_value=flag_value)
            # Just calling _get_state_enum already asserts 200; the assertion
            # below confirms data is a list (schema is well-formed).
            assert isinstance(enum, list)


# ---------------------------------------------------------------------------
# Regression guard: serializer still accepts state="review" as valid input
# ---------------------------------------------------------------------------


class TestEventSerializerStillAcceptsReviewState(BaseAPITest):
    """Changing the schema output must not break serializer input acceptance.

    Regardless of the feature flag, ``EventSerializer`` must continue to
    accept ``"review"`` as a valid state value so existing API clients and the
    community-input creation flow keep working.
    """

    def test_state_choices_include_sc_review(self) -> None:
        from activity.serializers import EventSerializer

        # EventSerializer.state is an auto-generated ChoiceField from the
        # model's CharField(choices=STATE_CHOICES).  Its valid choices are
        # in field.choices (a dict keyed by value).
        serializer = EventSerializer()
        state_field = serializer.fields["state"]
        valid_choices = list(state_field.choices.keys())
        assert (
            SC_REVIEW in valid_choices
        ), f"EventSerializer.state must accept {SC_REVIEW!r} regardless of the preview feature flag"

    def test_filter_specification_serializer_state_choices_include_sc_review(self) -> None:
        from activity.serializers.events import EventFilterSpecificationSerializer

        # EventFilterSpecificationSerializer.state is a ListField wrapping a
        # ChoiceField; the child ChoiceField carries the valid choices.
        serializer = EventFilterSpecificationSerializer()
        state_field = serializer.fields["state"]
        valid_choices = list(state_field.child.choices.keys())
        assert (
            SC_REVIEW in valid_choices
        ), f"EventFilterSpecificationSerializer.state must accept {SC_REVIEW!r} regardless of the preview feature flag"

    def test_review_is_in_event_state_choices_constant(self) -> None:
        choice_values = [s[0] for s in Event.STATE_CHOICES]
        assert SC_REVIEW in choice_values
