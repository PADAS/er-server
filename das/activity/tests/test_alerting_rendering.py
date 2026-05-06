"""Unit tests for activity.alerting.rendering (event rendering and state inference)."""

from unittest.mock import MagicMock, patch

from activity.alerting.rendering import infer_event_state, render_event
from activity.models import Event
from revision.manager import ACTION_ADDED, ACTION_UPDATED


class TestInferEventState:
    """Tests for infer_event_state branching logic."""

    def test_resolved_state_returned_as_is(self):
        event = MagicMock()
        event.state = Event.SC_RESOLVED
        assert infer_event_state(event) == Event.SC_RESOLVED

    def test_active_state_returned_as_is(self):
        event = MagicMock()
        event.state = Event.SC_ACTIVE
        assert infer_event_state(event) == Event.SC_ACTIVE

    def test_new_state_with_added_revision_stays_new(self):
        revision = MagicMock()
        revision.action = ACTION_ADDED

        event = MagicMock()
        event.state = Event.SC_NEW

        with patch(
            "activity.alerting.rendering.resolve_event_revisions",
            return_value=(revision, None),
        ):
            assert infer_event_state(event) == Event.SC_NEW

    def test_new_state_with_updated_revision_becomes_active(self):
        revision = MagicMock()
        revision.action = ACTION_UPDATED

        event = MagicMock()
        event.state = Event.SC_NEW

        with patch(
            "activity.alerting.rendering.resolve_event_revisions",
            return_value=(revision, None),
        ):
            assert infer_event_state(event) == Event.SC_ACTIVE

    def test_new_state_with_no_event_revision_becomes_active(self):
        """When resolve_event_revisions returns (None, details_rev), state is active."""
        details_revision = MagicMock()
        details_revision.action = ACTION_UPDATED

        event = MagicMock()
        event.state = Event.SC_NEW

        with patch(
            "activity.alerting.rendering.resolve_event_revisions",
            return_value=(None, details_revision),
        ):
            assert infer_event_state(event) == Event.SC_ACTIVE


class TestRenderEvent:
    """Tests for render_event permission gating and output shape."""

    def test_returns_none_when_permission_denied(self):
        event = MagicMock()
        user = MagicMock()

        with patch("activity.alerting.rendering.EventCategoryPermissions") as mock_perms:
            mock_perms.return_value.has_object_permission.return_value = False
            result = render_event(event, user)

        assert result is None

    def test_returns_event_data_with_inferred_state(self):
        event = MagicMock()
        user = MagicMock()

        fake_data = {"id": "123", "title": "Test"}

        with (
            patch("activity.alerting.rendering.EventCategoryPermissions") as mock_perms,
            patch("activity.alerting.rendering.EventSerializer") as mock_ser,
            patch(
                "activity.alerting.rendering.infer_event_state",
                return_value=Event.SC_NEW,
            ),
        ):
            mock_perms.return_value.has_object_permission.return_value = True
            mock_ser.return_value = MagicMock(data=dict(fake_data))

            result = render_event(event, user)

        assert result is not None
        assert result["id"] == "123"
        assert result["inferred_state"] == Event.SC_NEW
