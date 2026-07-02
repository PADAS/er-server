"""Tests for the V2 schema repair apply layer.

These tests cover :func:`~activity.schemas.migration.repair_apply.attempt_repair`
in isolation by mocking the upstream ``transform_schema`` / ``repair_v2_schema``
calls. For end-to-end tests that exercise the real upstream library against the
live ORM, see ``test_repair_upstream_integration.py``.
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
    SKIPPED_NEEDS_REVIEW,
    SKIPPED_NOT_MIGRATED,
    SKIPPED_USER_EDITED,
    attempt_repair,
)
from activity.schemas.ops.revision_history import EventTypeRevisionHistory
from revision.manager import ACTION_ADDED, ACTION_UPDATED

# Stable $ref URL shape (mirrors rewrite_field_to_ref)
_CHOICES_URL = "/api/v2.0/schemas/choices.json"

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

    def test_unparseable_v2_schema_is_skipped_as_user_edited_without_attempting_repair(self):
        """A REBUILD_FROM_V1-eligible history with an unparseable current V2 must
        be classified as SKIP_USER_EDITED and return SKIPPED_USER_EDITED immediately,
        without calling transform_schema or repair_v2_schema."""
        history = _history(
            [
                FakeRevision(1, ACTION_ADDED, {"schema": _v1_text(), "version": "1"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": _v2_text(), "version": "2"}),
            ]
        )
        with (
            patch.object(repair_apply, "transform_schema") as mock_transform,
            patch.object(repair_apply, "repair_v2_schema") as mock_repair,
        ):
            outcome = attempt_repair(history=history, schema_text="{bad json")

        assert outcome.action == SKIPPED_USER_EDITED
        assert outcome.new_schema_text is None
        mock_transform.assert_not_called()
        mock_repair.assert_not_called()


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


# ── attempt_repair: REBUILD_FROM_V1 — choice re-resolution ──────


def _v2_with_hardcoded_choice(field_name: str = "species") -> dict:
    """A V2 schema where a field has a hardcoded anyOf/oneOf (no $ref yet)."""
    return {
        "json": {
            "properties": {
                field_name: {
                    "title": field_name.title(),
                    "type": "string",
                    "anyOf": [
                        {
                            "title": "Hardcoded",
                            "type": "string",
                            "oneOf": [
                                {"const": "lion", "title": "Lion"},
                                {"const": "elephant", "title": "Elephant"},
                            ],
                        }
                    ],
                }
            }
        },
        "ui": {"fields": {field_name: {"type": "CHOICE_LIST"}}},
    }


def _v2_with_ref_choice(field_name: str = "species", ref_name: str = "species") -> dict:
    """A corrupted V2 schema whose json section already has a $ref for a choice field."""
    return {
        "json": {
            "properties": {
                field_name: {
                    "title": field_name.title(),
                    "type": "string",
                    "anyOf": [{"$ref": f"{_CHOICES_URL}?field={ref_name}"}],
                }
            }
        },
        "ui": {"fields": {field_name: {"type": "CHOICE_LIST"}}},
    }


class TestRebuildFromV1ChoiceReresolution:
    """REBUILD_FROM_V1: choice $ref re-derivation from the corrupted V2."""

    def _rebuild_history(self, v1_text: str, *, value: str = "x") -> EventTypeRevisionHistory:
        return _history(
            [
                FakeRevision(1, ACTION_ADDED, {"schema": v1_text, "version": "1"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": _v2_text(), "version": "2"}),
            ],
            event_type_value=value,
        )

    def test_hardcoded_choice_in_fresh_transform_is_rewritten_to_ref_from_corrupted_v2(self):
        """Regression: when the fresh transform emits a hardcoded-choice field AND
        the corrupted V2 (schema_text) has a $ref at that same path, the rebuilt
        schema's field must use the $ref, NOT the hardcoded oneOf."""
        v1 = _v1_text("species_report")
        # Fresh transform returns a V2 with a hardcoded anyOf/oneOf for 'species'.
        fresh_v2_with_hardcoded = _v2_with_hardcoded_choice("species")
        # The corrupted stored V2 already has a $ref pointing to 'species_list'.
        corrupted_v2 = _v2_with_ref_choice("species", ref_name="species_list")

        with (
            patch.object(repair_apply, "transform_schema", return_value=fresh_v2_with_hardcoded),
            patch.object(repair_apply, "preprocess_template_vars", side_effect=lambda x: x),
            patch.object(repair_apply, "LogCollector", side_effect=lambda *_a, **_kw: _StubCollector()),
        ):
            outcome = attempt_repair(
                history=self._rebuild_history(v1),
                schema_text=json.dumps(corrupted_v2),
            )

        assert outcome.action == APPLIED_REBUILT_FROM_V1
        assert outcome.did_apply
        rebuilt = json.loads(outcome.new_schema_text)
        species_field = rebuilt["json"]["properties"]["species"]
        # Must be a $ref, NOT the hardcoded oneOf.
        assert "anyOf" in species_field
        any_of = species_field["anyOf"]
        assert len(any_of) == 1
        assert "$ref" in any_of[0], f"Expected $ref but got: {any_of}"
        assert "species_list" in any_of[0]["$ref"], f"Expected ref to species_list but got: {any_of[0]['$ref']}"
        # Must not contain hardcoded oneOf.
        assert "oneOf" not in any_of[0]

    def test_hardcoded_choice_with_no_ref_in_corrupted_v2_left_as_hardcoded_and_reported(self):
        """When the fresh transform has a hardcoded choice but the corrupted V2 has
        NO $ref at that path, the field stays hardcoded. The path is added to
        metadata['unresolved_hardcoded_choice_paths'] and a warning is added.
        The action is still APPLIED_REBUILT_FROM_V1."""
        v1 = _v1_text("no_ref_report")
        fresh_v2_with_hardcoded = _v2_with_hardcoded_choice("species")
        # Corrupted V2 also has a hardcoded choice (no $ref).
        corrupted_v2_also_hardcoded = _v2_with_hardcoded_choice("species")

        with (
            patch.object(repair_apply, "transform_schema", return_value=fresh_v2_with_hardcoded),
            patch.object(repair_apply, "preprocess_template_vars", side_effect=lambda x: x),
            patch.object(repair_apply, "LogCollector", side_effect=lambda *_a, **_kw: _StubCollector()),
        ):
            outcome = attempt_repair(
                history=self._rebuild_history(v1),
                schema_text=json.dumps(corrupted_v2_also_hardcoded),
            )

        assert outcome.action == APPLIED_REBUILT_FROM_V1
        assert outcome.did_apply
        rebuilt = json.loads(outcome.new_schema_text)
        species_field = rebuilt["json"]["properties"]["species"]
        # Field remains hardcoded (no $ref).
        any_of = species_field["anyOf"]
        assert len(any_of) == 1
        assert "oneOf" in any_of[0], "Expected hardcoded oneOf to remain"
        # Unresolved path is in metadata.
        assert "unresolved_hardcoded_choice_paths" in outcome.metadata
        assert ["species"] in outcome.metadata["unresolved_hardcoded_choice_paths"]
        # A warning mentions the unresolved path.
        warnings = outcome.metadata.get("warnings", [])
        assert any("unresolved" in w.lower() or "species" in w for w in warnings), f"No warning found: {warnings}"

    def test_no_hardcoded_choices_in_fresh_transform_behaves_as_before(self):
        """When the fresh transform has NO hardcoded choices, re-resolution is a
        no-op and the outcome is unchanged from the pre-fix behavior."""
        v1 = _v1_text("plain_report")
        # A V2 with no anyOf at all — purely string fields.
        plain_v2 = {"json": {"properties": {"name": {"type": "string"}}}, "ui": {"fields": {"name": {}}}}
        corrupted_v2 = json.dumps({"json": {"properties": {"name": {"type": "string"}}}, "ui": {"fields": {}}})

        with (
            patch.object(repair_apply, "transform_schema", return_value=plain_v2),
            patch.object(repair_apply, "preprocess_template_vars", side_effect=lambda x: x),
            patch.object(repair_apply, "LogCollector", side_effect=lambda *_a, **_kw: _StubCollector()),
        ):
            outcome = attempt_repair(
                history=self._rebuild_history(v1),
                schema_text=corrupted_v2,
            )

        assert outcome.action == APPLIED_REBUILT_FROM_V1
        assert outcome.did_apply
        # No unresolved paths reported.
        assert "unresolved_hardcoded_choice_paths" not in outcome.metadata

    def test_collection_nested_hardcoded_choice_rewritten_via_corrupted_v2_ref(self):
        """A hardcoded choice nested inside a collection (property_path = ['trophies', 'species'])
        must also be re-derived from the corrupted V2's json section."""
        v1 = _v1_text("collection_choice_report")
        # Fresh transform: collection field with nested hardcoded choice.
        fresh_v2_collection = {
            "json": {
                "properties": {
                    "trophies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "species_seen": {
                                    "title": "Species Seen",
                                    "type": "string",
                                    "anyOf": [
                                        {
                                            "title": "Hardcoded",
                                            "type": "string",
                                            "oneOf": [
                                                {"const": "lion", "title": "Lion"},
                                                {"const": "elephant", "title": "Elephant"},
                                            ],
                                        }
                                    ],
                                }
                            },
                        },
                    }
                }
            },
            "ui": {"fields": {}},
        }
        # Corrupted V2: the nested field already has a $ref.
        corrupted_v2_with_nested_ref = {
            "json": {
                "properties": {
                    "trophies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "species_seen": {
                                    "title": "Species Seen",
                                    "type": "string",
                                    "anyOf": [{"$ref": f"{_CHOICES_URL}?field=trophy_species"}],
                                }
                            },
                        },
                    }
                }
            },
            "ui": {"fields": {}},
        }

        with (
            patch.object(repair_apply, "transform_schema", return_value=fresh_v2_collection),
            patch.object(repair_apply, "preprocess_template_vars", side_effect=lambda x: x),
            patch.object(repair_apply, "LogCollector", side_effect=lambda *_a, **_kw: _StubCollector()),
        ):
            outcome = attempt_repair(
                history=self._rebuild_history(v1),
                schema_text=json.dumps(corrupted_v2_with_nested_ref),
            )

        assert outcome.action == APPLIED_REBUILT_FROM_V1
        assert outcome.did_apply
        rebuilt = json.loads(outcome.new_schema_text)
        nested_field = rebuilt["json"]["properties"]["trophies"]["items"]["properties"]["species_seen"]
        any_of = nested_field["anyOf"]
        assert len(any_of) == 1
        assert "$ref" in any_of[0], f"Nested field not rewritten to $ref: {any_of}"
        assert "trophy_species" in any_of[0]["$ref"]
        assert "oneOf" not in any_of[0]


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

        with patch.object(repair_apply, "repair_v2_schema", repair_mock):
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

    def test_no_op_when_upstream_returns_unmodified_empty_changes(self):
        fake_result = MagicMock(was_modified=False, repaired_schema=None, changes=[])
        with patch.object(repair_apply, "repair_v2_schema", return_value=fake_result):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == SKIPPED_ALREADY_CORRECT
        assert outcome.new_schema_text is None
        assert outcome.metadata["upstream_changes"] == 0

    def test_records_repair_exception(self):
        def boom(*_a, **_kw):
            raise RuntimeError("upstream blew up")

        with patch.object(repair_apply, "repair_v2_schema", side_effect=boom):
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

        with patch.object(
            repair_apply,
            "repair_v2_schema",
            side_effect=populate_logger_errors,
        ):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == ERROR_REPAIR
        assert any("leftColumn" in e for e in outcome.errors)
        assert outcome.new_schema_text is None

    def test_diagnostics_with_no_mutation_returns_skipped_needs_review(self):
        """was_modified=False with non-empty changes → SKIPPED_NEEDS_REVIEW.

        Per the 0.1.5.2 contract: changes can be non-empty even when
        was_modified=False. Those entries are diagnostics (e.g.
        ``ambiguous_collision_kept``) representing corruption beyond the
        collection-key bug that repair refuses to auto-fix.
        """
        diagnostic_change = MagicMock(
            spec=["action", "field_path", "details"],
            action="ambiguous_collision_kept",
            field_path="num",
            details="'num' is both a root field and a collection orphan; kept for manual review",
        )
        fake_result = MagicMock(
            was_modified=False,
            repaired_schema=None,
            changes=[diagnostic_change],
        )
        with patch.object(repair_apply, "repair_v2_schema", return_value=fake_result):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == SKIPPED_NEEDS_REVIEW
        assert outcome.new_schema_text is None
        assert outcome.metadata["upstream_changes"] == 1
        assert outcome.metadata["upstream_change_summary"] == [
            {
                "action": "ambiguous_collision_kept",
                "field_path": "num",
                "details": "'num' is both a root field and a collection orphan; kept for manual review",
            }
        ]

    def test_diagnostics_change_count_matches_changes_length(self):
        """upstream_changes reflects actual len(changes), not a hardcoded 0."""
        changes = [
            MagicMock(
                spec=["action", "field_path", "details"], action="skipped_unknown_type", field_path=f"f{i}", details=""
            )
            for i in range(3)
        ]
        fake_result = MagicMock(was_modified=False, repaired_schema=None, changes=changes)
        with patch.object(repair_apply, "repair_v2_schema", return_value=fake_result):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == SKIPPED_NEEDS_REVIEW
        assert outcome.metadata["upstream_changes"] == 3
        assert len(outcome.metadata["upstream_change_summary"]) == 3

    def test_warnings_from_log_collector_surfaced_on_applied_repair(self):
        """Warnings from the LogCollector appear in metadata on an applied repair.

        A warning alone (no errors) must NOT fail the repair — warnings
        flag lossy-but-correct operations (e.g. rebuilt COLLECTION containers
        with defaults).
        """
        repaired = {"json": {}, "ui": {"fields": {"f": {"type": "COLLECTION"}}}}
        change = MagicMock(
            spec=["action", "field_path", "details"],
            action="rebuilt_collection_entry",
            field_path="trophies",
            details="",
        )
        fake_result = MagicMock(was_modified=True, repaired_schema=repaired, changes=[change])

        def emit_warning(_schema, *, logger):
            logger.log_warning("Rebuilt COLLECTION 'trophies' with defaults; V1 originals unrecoverable")
            return fake_result

        with patch.object(repair_apply, "repair_v2_schema", side_effect=emit_warning):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == APPLIED_RECONSTRUCTED_FROM_JSON
        assert outcome.did_apply
        assert "warnings" in outcome.metadata
        assert any("trophies" in w for w in outcome.metadata["warnings"])

    def test_warnings_surfaced_on_skipped_needs_review(self):
        """Warnings from the LogCollector also appear on a needs-review skip."""
        diagnostic_change = MagicMock(
            spec=["action", "field_path", "details"],
            action="ambiguous_collision_kept",
            field_path="count",
            details="kept for manual review",
        )
        fake_result = MagicMock(was_modified=False, repaired_schema=None, changes=[diagnostic_change])

        def emit_warning(_schema, *, logger):
            logger.log_warning("Un-prefixed entry 'count' collides with a root-level field")
            return fake_result

        with patch.object(repair_apply, "repair_v2_schema", side_effect=emit_warning):
            outcome = attempt_repair(
                history=self._json_reconstruction_history(),
                schema_text=_v2_text(),
            )
        assert outcome.action == SKIPPED_NEEDS_REVIEW
        assert "warnings" in outcome.metadata
        assert any("count" in w for w in outcome.metadata["warnings"])


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
