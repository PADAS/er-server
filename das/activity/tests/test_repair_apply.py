"""Tests for the V2 schema repair apply layer.

The migration smoke-test that exercised ``repair_v2_collection_schemas()``
was moved out of this file together with the repair migration (it now lives
on the develop branch). On this hotfix branch the ``0202`` migration is a
no-op, so this file no longer imports it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from activity.schemas.migration import repair_apply
from activity.schemas.migration.repair import RepairStrategy
from activity.schemas.migration.repair_apply import (
    APPLIED_REBUILT_FROM_V1,
    APPLIED_RECONSTRUCTED_FROM_JSON,
    ERROR_PARSE,
    ERROR_REPAIR,
    ERROR_TRANSFORM,
    SKIPPED_ALREADY_CORRECT,
    SKIPPED_JSON_RECONSTRUCTION_DEFERRED,
    SKIPPED_NOT_MIGRATED,
    SKIPPED_USER_EDITED,
    attempt_repair,
)
from activity.schemas.ops.revision_history import EventTypeRevisionHistory
from revision.manager import ACTION_ADDED, ACTION_UPDATED

# ── Test stubs ────────────────────────────────────────────────────────────


@dataclass
class FakeRevision:
    sequence: int
    action: str
    data: dict[str, Any]


def _history(
    revisions: list[FakeRevision],
    *,
    event_type_value: str = "x",
) -> EventTypeRevisionHistory:
    """Test helper: build a history with a stable id.

    The id is fixed so test assertions on classification.event_type_id
    (when any are added later) can pin the value, and so test failures
    don't carry randomized noise.
    """
    return EventTypeRevisionHistory.from_revisions(
        event_type_value=event_type_value,
        event_type_id=str(uuid4()),
        revisions=revisions,
    )


def _v1_text(marker: str = "v1") -> str:
    return json.dumps(
        {
            "schema": {
                "type": "object",
                "properties": {marker: {"type": "string", "title": marker.title()}},
            },
            "definition": [marker],
        }
    )


def _v2_text(marker: str = "v2") -> str:
    return json.dumps(
        {
            "json": {"properties": {marker: {"type": "string"}}},
            "ui": {"fields": {}},
        }
    )


# ── attempt_repair: routing tests ────────────────────────────────────────


class TestAttemptRepairRouting:
    """Confirm tier dispatch routes to the correct outcome action."""

    def test_not_migrated_returns_no_op(self):
        history = _history([FakeRevision(1, ACTION_ADDED, {"schema": _v2_text(), "version": "2"})])
        outcome = attempt_repair(history=history, schema_text=_v2_text())
        assert outcome.action == SKIPPED_NOT_MIGRATED
        assert outcome.new_schema_text is None
        assert outcome.did_apply is False

    def test_user_edited_skipped(self):
        history = _history(
            [
                FakeRevision(1, ACTION_ADDED, {"schema": _v1_text(), "version": "1"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": _v2_text(), "version": "2"}),
                FakeRevision(3, ACTION_UPDATED, {"schema": _v2_text("user")}),
            ]
        )
        outcome = attempt_repair(history=history, schema_text=_v2_text("user"))
        assert outcome.action == SKIPPED_USER_EDITED
        assert outcome.classification.strategy == RepairStrategy.SKIP_USER_EDITED


# ── attempt_repair: REBUILD_FROM_V1 ─────────────────────────────


class TestAttemptRepairRebuildFromV1:
    """REBUILD_FROM_V1: re-run transform_schema against reconstructed V1."""

    def _rebuild_history(self, v1_text: str, *, value: str = "x") -> EventTypeRevisionHistory:
        return _history(
            [
                FakeRevision(1, ACTION_ADDED, {"schema": v1_text, "version": "1"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": _v2_text(), "version": "2"}),
            ],
            event_type_value=value,
        )

    def test_invokes_transform_and_returns_new_schema(self):
        v1 = _v1_text("animal")
        sentinel_v2 = {"json": {"properties": {"animal": {"type": "string"}}}, "ui": {"fields": {"animal": {}}}}

        with (
            patch.object(repair_apply, "transform_schema") as mock_transform,
            patch.object(repair_apply, "preprocess_template_vars", side_effect=lambda x: x),
            patch.object(repair_apply, "LogCollector", side_effect=lambda *_args, **_kwargs: _StubCollector()),
        ):
            mock_transform.return_value = sentinel_v2
            outcome = attempt_repair(
                history=self._rebuild_history(v1, value="animal_report"),
                schema_text=_v2_text(),
            )

        assert outcome.action == APPLIED_REBUILT_FROM_V1
        assert outcome.did_apply
        assert outcome.new_schema_text is not None
        assert json.loads(outcome.new_schema_text) == sentinel_v2
        mock_transform.assert_called_once()
        assert mock_transform.call_args.args[0] == json.loads(v1)

    def test_records_transform_errors(self):
        with (
            patch.object(repair_apply, "transform_schema", return_value={}),
            patch.object(repair_apply, "preprocess_template_vars", side_effect=lambda x: x),
            patch.object(
                repair_apply,
                "LogCollector",
                side_effect=lambda *_a, **_kw: _StubCollector(errors=[{"message": "bad reference"}]),
            ),
        ):
            outcome = attempt_repair(
                history=self._rebuild_history(_v1_text()),
                schema_text=_v2_text(),
            )
        assert outcome.action == ERROR_TRANSFORM
        assert outcome.errors == ["bad reference"]
        assert outcome.new_schema_text is None

    def test_handles_invalid_reconstructed_v1_json(self):
        # REBUILD_FROM_V1 history but with malformed V1 text in the snapshot.
        history = _history(
            [
                FakeRevision(1, ACTION_ADDED, {"schema": "not-json{", "version": "1"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": _v2_text(), "version": "2"}),
            ]
        )
        with patch.object(repair_apply, "preprocess_template_vars", side_effect=lambda x: x):
            outcome = attempt_repair(history=history, schema_text=_v2_text())
        assert outcome.action == ERROR_PARSE
        assert outcome.new_schema_text is None

    def test_propagates_transform_warnings_in_metadata(self):
        sentinel_v2 = {"json": {}, "ui": {"fields": {}}}
        with (
            patch.object(repair_apply, "transform_schema", return_value=sentinel_v2),
            patch.object(repair_apply, "preprocess_template_vars", side_effect=lambda x: x),
            patch.object(
                repair_apply,
                "LogCollector",
                side_effect=lambda *_a, **_kw: _StubCollector(warnings=[{"message": "deprecated widget"}]),
            ),
        ):
            outcome = attempt_repair(
                history=self._rebuild_history(_v1_text()),
                schema_text=_v2_text(),
            )
        assert outcome.action == APPLIED_REBUILT_FROM_V1
        assert outcome.metadata.get("warnings") == ["deprecated widget"]


# ── attempt_repair: RECONSTRUCT_FROM_JSON ───────────────────────


class TestAttemptRepairReconstructFromJson:
    """RECONSTRUCT_FROM_JSON: hand the V2 schema to the upstream
    repair_v2_schema utility, which infers ui.fields from the JSON section.
    """

    def _json_reconstruction_history(self) -> EventTypeRevisionHistory:
        # Snapshot lacks "schema" → V1 reconstruction impossible →
        # falls through to RECONSTRUCT_FROM_JSON.
        return _history(
            [
                FakeRevision(1, ACTION_ADDED, {"display": "x"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": _v2_text(), "version": "2"}),
            ]
        )

    def test_deferred_when_upstream_missing(self):
        with patch.object(repair_apply, "REPAIR_V2_AVAILABLE", False):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == SKIPPED_JSON_RECONSTRUCTION_DEFERRED
        assert outcome.metadata.get("repair_v2_available") is False

    def test_applies_repaired_schema(self):
        # Use a real RepairChange-shaped object so getattr() returns the
        # documented fields rather than MagicMock auto-attributes.
        change = MagicMock(
            spec=["action", "field_path", "details"],
            action="rebuilt_ui_entry",
            field_path="wildlife_trophies.species",
            details="Inferred TEXT/SHORT_TEXT from json type 'string'",
        )
        repaired = {"json": {"properties": {}}, "ui": {"fields": {"f": {"type": "TEXT"}}}}
        fake_result = MagicMock(
            was_modified=True,
            repaired_schema=repaired,
            changes=[change],
        )
        repair_mock = MagicMock(return_value=fake_result)

        with (
            patch.object(repair_apply, "REPAIR_V2_AVAILABLE", True),
            patch.object(repair_apply, "repair_v2_schema", repair_mock, create=True),
        ):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )

        assert outcome.action == APPLIED_RECONSTRUCTED_FROM_JSON
        assert outcome.did_apply
        assert outcome.new_schema_text is not None
        assert json.loads(outcome.new_schema_text) == repaired
        assert outcome.metadata["upstream_changes"] == 1
        # Per docs/architecture/v2-schema-repair-upstream-contract.md the
        # change summary should expose the documented RepairChange fields
        # verbatim for log correlation.
        assert outcome.metadata["upstream_change_summary"] == [
            {
                "action": "rebuilt_ui_entry",
                "field_path": "wildlife_trophies.species",
                "details": "Inferred TEXT/SHORT_TEXT from json type 'string'",
            }
        ]
        # The team's contract requires the logger to be passed by keyword
        # so the upstream module can collect errors without raising.
        _, kwargs = repair_mock.call_args
        assert "logger" in kwargs

    def test_no_op_when_upstream_returns_unmodified(self):
        fake_result = MagicMock(was_modified=False, repaired_schema=None, changes=[])
        with (
            patch.object(repair_apply, "REPAIR_V2_AVAILABLE", True),
            patch.object(repair_apply, "repair_v2_schema", return_value=fake_result, create=True),
        ):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == SKIPPED_ALREADY_CORRECT
        assert outcome.new_schema_text is None

    def test_records_repair_exception(self):
        def boom(*_a, **_kw):
            raise RuntimeError("upstream blew up")

        with (
            patch.object(repair_apply, "REPAIR_V2_AVAILABLE", True),
            patch.object(repair_apply, "repair_v2_schema", side_effect=boom, create=True),
        ):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == ERROR_REPAIR
        assert "upstream blew up" in outcome.errors[0]

    def test_records_logger_errors(self):
        """The team's contract reports errors via LogCollector, not exceptions."""
        repaired = {"json": {}, "ui": {"fields": {}}}
        fake_result = MagicMock(was_modified=True, repaired_schema=repaired, changes=[])

        def populate_logger_errors(_schema, *, logger):
            # The real LogCollector exposes ``log_error`` (not ``error``);
            # confirmed by inspecting schema_migration_tool.utils.logger.
            logger.log_error("Inconsistent leftColumn references")
            return fake_result

        with (
            patch.object(repair_apply, "REPAIR_V2_AVAILABLE", True),
            patch.object(
                repair_apply,
                "repair_v2_schema",
                side_effect=populate_logger_errors,
                create=True,
            ),
        ):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == ERROR_REPAIR
        assert any("leftColumn" in e for e in outcome.errors)
        assert outcome.new_schema_text is None


# ── Test helpers ──────────────────────────────────────────────────────────


class _StubCollector:
    """Minimal LogCollector stand-in for transform_schema mocking."""

    def __init__(self, *, errors: list | None = None, warnings: list | None = None):
        self._errors = errors or []
        self._warnings = warnings or []

    def get_errors(self):
        return self._errors

    def get_warnings(self):
        return self._warnings

    def get_features(self):
        return {}
