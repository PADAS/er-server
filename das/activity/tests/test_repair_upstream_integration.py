"""Integration tests that exercise the REAL upstream repair library.

Unlike ``test_repair_apply.py`` (which mocks ``transform_schema`` /
``repair_v2_schema`` to test routing in isolation), this module calls the
actual pinned ``event-type-schema-migration-tool`` (==0.1.5.2) end-to-end.

It is the deep-testing safety net for the release branch: it proves that

* ``RepairStrategy.RECONSTRUCT_FROM_JSON`` produces a correctly
  dot-prefixed ``ui.fields`` map when handed a *realistically corrupted*
  V2 collection schema (the pre-0.1.4 bug reproduced by hand), and that
  the ``json`` section is left byte-for-byte intact;
* ``RepairStrategy.REBUILD_FROM_V1`` re-runs the fixed migration against a
  reconstructed V1 collection schema and emits prefixed nested IDs;
* the repair is idempotent (a second pass reports ``was_modified=False``);
* the ``0203`` data migration drives all of the above through the real
  ORM + real upstream, applying the right action per strategy.

If the upstream contract changes shape (``RepairChange`` fields, the
``LogCollector`` error dict, the prefixing convention) these tests fail
loudly rather than silently passing on stale mocks. See
``docs/architecture/v2-schema-repair-upstream-contract.md``.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from activity.models import EventType
from activity.schemas.migration.repair import RepairStrategy
from activity.schemas.migration.repair_apply import (
    APPLIED_REBUILT_FROM_V1,
    APPLIED_RECONSTRUCTED_FROM_JSON,
    SKIPPED_ALREADY_CORRECT,
    SKIPPED_NEEDS_REVIEW,
    attempt_repair,
)
from activity.schemas.ops.revision_history import EventTypeRevisionHistory
from factories import EventTypeFactory
from revision.manager import ACTION_ADDED, ACTION_UPDATED

_migration_module = importlib.import_module("activity.migrations.0203_repair_v2_collection_schemas")
run_repair_migration = _migration_module.repair_v2_collection_schemas


def _historical_apps():
    """App-registry state that ``RunPython`` hands the 0203 migration body
    (the project state as of its parent migration). Using this instead of the
    live ``django.apps.apps`` reproduces the historical ``__fake__`` models, so
    these tests exercise the real migration surface."""
    return MigrationExecutor(connection).loader.project_state(("activity", "0202_repair_v2_collection_schemas")).apps


# ── Test stubs / fixtures ─────────────────────────────────────────────────


@dataclass
class FakeRevision:
    sequence: int
    action: str
    data: dict[str, Any]


def _v1_collection_text(collection: str = "wildlife_trophies") -> str:
    """A realistic V1 schema with one array-of-object (collection) field."""
    return json.dumps(
        {
            "schema": {
                "type": "object",
                "properties": {
                    "incident_title": {"type": "string", "title": "Incident Title"},
                    collection: {
                        "type": "array",
                        "title": "Trophies",
                        "items": {
                            "type": "object",
                            "properties": {
                                "species": {"type": "string", "title": "Species"},
                                "count": {"type": "number", "title": "Count"},
                            },
                        },
                    },
                },
            },
            "definition": ["incident_title", collection],
        }
    )


def _corrupted_v2_collection_text(collection: str = "wildlife_trophies") -> str:
    """A V2 schema reproducing the pre-0.1.4 collection bug.

    The ``json`` section is correct (the source of truth). The
    ``ui.fields`` map stores the nested children under *un-prefixed*
    local keys (``species`` / ``count`` instead of
    ``wildlife_trophies.species`` / ``wildlife_trophies.count``) and the
    COLLECTION's ``leftColumn`` points at those broken keys — exactly the
    shape ``repair_v2_schema`` is built to detect and fix.
    """
    return json.dumps(
        {
            "json": {
                "type": "object",
                "properties": {
                    "incident_title": {"type": "string", "title": "Incident Title"},
                    collection: {
                        "type": "array",
                        "title": "Trophies",
                        "items": {
                            "type": "object",
                            "properties": {
                                "species": {"type": "string", "title": "Species"},
                                "count": {"type": "number", "title": "Count"},
                            },
                        },
                    },
                },
            },
            "ui": {
                "fields": {
                    "incident_title": {"type": "TEXT", "inputType": "SHORT_TEXT", "parent": "section-1"},
                    "species": {"type": "TEXT", "inputType": "SHORT_TEXT", "parent": collection},
                    "count": {"type": "NUMERIC", "parent": collection},
                    collection: {
                        "type": "COLLECTION",
                        "parent": "section-1",
                        "leftColumn": ["species", "count"],
                        "rightColumn": [],
                    },
                }
            },
        }
    )


def _history(revisions: list[FakeRevision], *, value: str = "evidence") -> EventTypeRevisionHistory:
    return EventTypeRevisionHistory.from_revisions(
        event_type_value=value,
        event_type_id=str(uuid4()),
        revisions=revisions,
    )


def _assert_collection_repaired(fields: dict[str, Any], collection: str = "wildlife_trophies") -> None:
    """Shared assertions for a correctly repaired collection ui.fields map."""
    # Nested children are now dot-prefixed.
    assert f"{collection}.species" in fields
    assert f"{collection}.count" in fields
    # The COLLECTION's leftColumn references the prefixed keys.
    assert fields[collection]["leftColumn"] == [f"{collection}.species", f"{collection}.count"]
    # Stale un-prefixed nested entries are gone (root field stays).
    assert "species" not in fields
    assert "count" not in fields
    assert "incident_title" in fields


# ── RECONSTRUCT_FROM_JSON against the real repair_v2_schema ───────────────


class TestReconstructFromJsonRealUpstream:
    def _reconstruct_history(self) -> EventTypeRevisionHistory:
        # Creation snapshot lacks "schema" → V1 is not reconstructable →
        # classification falls through to RECONSTRUCT_FROM_JSON.
        return _history(
            [
                FakeRevision(1, ACTION_ADDED, {"display": "Evidence"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": _corrupted_v2_collection_text(), "version": "2"}),
            ]
        )

    def test_repairs_corrupted_collection_ui_fields(self):
        outcome = attempt_repair(
            history=self._reconstruct_history(),
            schema_text=_corrupted_v2_collection_text(),
        )

        assert outcome.classification.strategy == RepairStrategy.RECONSTRUCT_FROM_JSON
        assert outcome.action == APPLIED_RECONSTRUCTED_FROM_JSON
        assert outcome.did_apply

        repaired = json.loads(outcome.new_schema_text)
        _assert_collection_repaired(repaired["ui"]["fields"])
        # The JSON section is the source of truth and must be untouched.
        assert repaired["json"] == json.loads(_corrupted_v2_collection_text())["json"]
        # Upstream change summary is surfaced for log correlation.
        assert outcome.metadata["upstream_changes"] >= 1

    def test_idempotent_second_pass_is_no_op(self):
        first = attempt_repair(
            history=self._reconstruct_history(),
            schema_text=_corrupted_v2_collection_text(),
        )
        assert first.action == APPLIED_RECONSTRUCTED_FROM_JSON

        # Feed the already-repaired schema back in: upstream must report
        # was_modified=False, so we skip as already-correct.
        second = attempt_repair(
            history=self._reconstruct_history(),
            schema_text=first.new_schema_text,
        )
        assert second.action == SKIPPED_ALREADY_CORRECT
        assert second.new_schema_text is None
        assert second.metadata.get("upstream_changes") == 0

    def test_harvest_then_infer_preserves_surviving_ui_data(self):
        """Harvest-then-infer: UI data from surviving un-prefixed entries is
        recovered losslessly into the rebuilt prefixed entry.

        The 0.1.5.2 contract guarantees: if the mis-keyed original still
        survives in ``ui.fields``, its ``inputType``, ``placeholder``, etc.
        are harvested and preserved in the rebuilt entry — only true collision
        victims (original destroyed) fall back to JSON-inferred defaults.

        This test uses ``inputType: LONG_TEXT`` and a ``placeholder``, which
        the JSON section cannot encode (``"type": "string"`` is ambiguous), to
        verify that harvest takes priority over inference.
        """
        # Corrupted V2: the collection child "notes" survives un-prefixed with
        # LONG_TEXT and a placeholder that JSON cannot encode.
        corrupted = {
            "json": {
                "type": "object",
                "properties": {
                    "observations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "notes": {"type": "string"},
                                "count": {"type": "number"},
                            },
                        },
                    }
                },
            },
            "ui": {
                "fields": {
                    "observations": {
                        "type": "COLLECTION",
                        "leftColumn": ["notes", "count"],
                    },
                    # Un-prefixed survivors carrying UI data JSON cannot encode.
                    "notes": {
                        "type": "TEXT",
                        "inputType": "LONG_TEXT",
                        "placeholder": "Enter field notes",
                        "parent": "observations",
                    },
                    "count": {"type": "NUMERIC", "parent": "observations"},
                }
            },
        }
        history = _history(
            [
                FakeRevision(1, ACTION_ADDED, {"display": "Observations"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": json.dumps(corrupted), "version": "2"}),
            ]
        )

        outcome = attempt_repair(history=history, schema_text=json.dumps(corrupted))

        assert outcome.action == APPLIED_RECONSTRUCTED_FROM_JSON
        assert outcome.did_apply

        fields = json.loads(outcome.new_schema_text)["ui"]["fields"]
        rebuilt_notes = fields.get("observations.notes")
        assert rebuilt_notes is not None, "Expected 'observations.notes' in repaired fields"
        # Harvest-then-infer: LONG_TEXT must be recovered from the surviving entry,
        # not fallen back to the JSON-inferred SHORT_TEXT default.
        assert (
            rebuilt_notes.get("inputType") == "LONG_TEXT"
        ), f"Expected harvested LONG_TEXT but got: {rebuilt_notes.get('inputType')!r}"
        # Placeholder is also harvested (JSON has no signal for this).
        assert (
            rebuilt_notes.get("placeholder") == "Enter field notes"
        ), f"Expected harvested placeholder but got: {rebuilt_notes.get('placeholder')!r}"
        # Un-prefixed orphan must be removed.
        assert "notes" not in fields, "Un-prefixed orphan 'notes' should have been removed"

    def test_diagnostics_only_schema_returns_skipped_needs_review(self):
        """was_modified=False with diagnostic changes → SKIPPED_NEEDS_REVIEW.

        Constructs a schema where an un-prefixed entry collides with a root-level
        field of the same name (``ambiguous_collision_kept``): the repair tool
        diagnoses it but refuses to auto-fix. Per the 0.1.5.2 contract this
        produces ``was_modified=False`` with a non-empty ``changes`` list.
        """
        # A schema where repair leaves everything untouched (already-prefixed
        # entries are correct) but reports an ambiguous collision diagnostic.
        v2_with_diagnostic = {
            "json": {
                "type": "object",
                "properties": {
                    # Root-level field named "num"
                    "num": {"type": "number"},
                    "wildlife_trophies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"num": {"type": "number"}},
                        },
                    },
                },
            },
            "ui": {
                "fields": {
                    # Correctly-prefixed entry already present — not rebuilt.
                    "wildlife_trophies.num": {"type": "NUMERIC", "parent": "wildlife_trophies"},
                    "wildlife_trophies": {
                        "type": "COLLECTION",
                        "leftColumn": ["wildlife_trophies.num"],
                    },
                    # Un-prefixed entry ambiguous: root-level field name + parented
                    # to the collection — diagnosed but left untouched.
                    "num": {"type": "NUMERIC", "parent": "wildlife_trophies"},
                }
            },
        }
        history = _history(
            [
                FakeRevision(1, ACTION_ADDED, {"display": "Trophies"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": json.dumps(v2_with_diagnostic), "version": "2"}),
            ]
        )

        outcome = attempt_repair(history=history, schema_text=json.dumps(v2_with_diagnostic))

        assert outcome.action == SKIPPED_NEEDS_REVIEW, (
            f"Expected SKIPPED_NEEDS_REVIEW but got {outcome.action!r}. " f"Metadata: {outcome.metadata}"
        )
        assert outcome.new_schema_text is None
        assert outcome.metadata["upstream_changes"] >= 1
        summary_actions = [c["action"] for c in outcome.metadata.get("upstream_change_summary", [])]
        assert "ambiguous_collision_kept" in summary_actions


# ── REBUILD_FROM_V1 against the real transform_schema ─────────────────────


class TestRebuildFromV1RealUpstream:
    def test_remigrates_reconstructed_v1_into_clean_v2(self):
        v1 = _v1_collection_text()
        history = _history(
            [
                FakeRevision(1, ACTION_ADDED, {"schema": v1, "version": "1"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": _corrupted_v2_collection_text(), "version": "2"}),
            ],
            value="trophy_report",
        )

        outcome = attempt_repair(history=history, schema_text=_corrupted_v2_collection_text())

        assert outcome.classification.strategy == RepairStrategy.REBUILD_FROM_V1
        assert outcome.action == APPLIED_REBUILT_FROM_V1
        assert outcome.did_apply

        rebuilt = json.loads(outcome.new_schema_text)
        # The fixed migration emits dot-prefixed nested IDs.
        fields = rebuilt["ui"]["fields"]
        assert "wildlife_trophies.species" in fields
        assert "wildlife_trophies.count" in fields
        assert fields["wildlife_trophies"]["type"] == "COLLECTION"

    def test_choice_ref_re_derived_from_corrupted_v2_and_collection_fixed(self):
        """Real transform_schema: V1 with an enum/enumNames choice field PLUS a
        collection field.  The corrupted V2 supplied as schema_text has the correct
        $ref for the choice field (as the original migration would have written it).

        After repair the rebuilt schema must:
        (a) have the collection ui.fields prefixed correctly, AND
        (b) have the choice field as a $ref (re-derived from the corrupted V2),
            NOT as a hardcoded anyOf/oneOf.

        This exercises the real 0.1.5.2 transform_schema pipeline end-to-end.
        """
        # V1 schema: one enum/enumNames choice field + one collection field.
        v1_with_choice_and_collection = json.dumps(
            {
                "schema": {
                    "type": "object",
                    "properties": {
                        "incident_title": {"type": "string", "title": "Incident Title"},
                        "species": {
                            "type": "string",
                            "title": "Species",
                            "enum": ["lion", "elephant", "zebra"],
                            "enumNames": ["Lion", "Elephant", "Zebra"],
                        },
                        "wildlife_trophies": {
                            "type": "array",
                            "title": "Trophies",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "count": {"type": "number", "title": "Count"},
                                },
                            },
                        },
                    },
                },
                "definition": ["incident_title", "species", "wildlife_trophies"],
            }
        )

        # Corrupted V2: json section has the resolved $ref for 'species' (as the
        # original migration would have written after rewrite_resolved_choice_refs).
        # The ui.fields section has the collection bug (un-prefixed children).
        # The $ref URL path must match what reverse('schemas:choices') returns.
        choices_url = "/api/v2.0/schemas/choices.json"
        corrupted_v2 = json.dumps(
            {
                "json": {
                    "type": "object",
                    "properties": {
                        "incident_title": {"type": "string", "title": "Incident Title"},
                        "species": {
                            "title": "Species",
                            "type": "string",
                            # $ref as the original migration would have written it.
                            "anyOf": [{"$ref": f"{choices_url}?field=trophy_species_list"}],
                        },
                        "wildlife_trophies": {
                            "type": "array",
                            "title": "Trophies",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "count": {"type": "number", "title": "Count"},
                                },
                            },
                        },
                    },
                },
                "ui": {
                    "fields": {
                        "incident_title": {"type": "TEXT", "inputType": "SHORT_TEXT", "parent": "section-1"},
                        "species": {"type": "CHOICE_LIST", "parent": "section-1"},
                        # Collection bug: un-prefixed child.
                        "count": {"type": "NUMERIC", "parent": "wildlife_trophies"},
                        "wildlife_trophies": {
                            "type": "COLLECTION",
                            "parent": "section-1",
                            "leftColumn": ["count"],
                            "rightColumn": [],
                        },
                    }
                },
            }
        )

        history = _history(
            [
                FakeRevision(1, ACTION_ADDED, {"schema": v1_with_choice_and_collection, "version": "1"}),
                FakeRevision(2, ACTION_UPDATED, {"schema": corrupted_v2, "version": "2"}),
            ],
            value="trophy_choice_report",
        )

        outcome = attempt_repair(history=history, schema_text=corrupted_v2)

        assert outcome.classification.strategy == RepairStrategy.REBUILD_FROM_V1
        assert outcome.action == APPLIED_REBUILT_FROM_V1
        assert outcome.did_apply

        rebuilt = json.loads(outcome.new_schema_text)

        # (a) Collection ui.fields must be correctly prefixed.
        fields = rebuilt["ui"]["fields"]
        assert "wildlife_trophies.count" in fields, f"Expected dot-prefixed child in fields: {list(fields)}"
        assert "count" not in fields, "Un-prefixed 'count' should be gone after repair"
        assert fields["wildlife_trophies"]["type"] == "COLLECTION"

        # (b) The choice field must come out as $ref, NOT hardcoded oneOf.
        species_field = rebuilt["json"]["properties"]["species"]
        any_of = species_field.get("anyOf", [])
        assert len(any_of) == 1, f"Expected single anyOf entry: {any_of}"
        ref_entry = any_of[0]
        assert "$ref" in ref_entry, (
            f"Expected $ref (re-derived from corrupted V2) but got hardcoded anyOf: {ref_entry}. "
            "This means the real transform_schema emitted a hardcoded shape that "
            "ChoiceProcessor did not detect — check _extract_field_hardcoded_choices."
        )
        assert (
            "trophy_species_list" in ref_entry["$ref"]
        ), f"Expected ref to 'trophy_species_list' but got: {ref_entry['$ref']}"
        assert "oneOf" not in ref_entry, "Field must not contain hardcoded oneOf after re-resolution"


# ── Full data migration through real ORM + real upstream ──────────────────


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestMigrationRealUpstream:
    """Run ``0203`` with no mocking — real revisions, real upstream tool."""

    def _migrate_v1_to_corrupted_v2(self, value: str, *, post_edit: bool = False) -> EventType:
        et = EventTypeFactory.create(
            value=value,
            schema=_v1_collection_text(),
            version=EventType.VersionChoices.VERSION_1,
        )
        et.schema = _corrupted_v2_collection_text()
        et.version = EventType.VersionChoices.VERSION_2
        et.save()
        if post_edit:
            # A post-migration user edit — must be respected (skipped).
            et.schema = _corrupted_v2_collection_text("user_added_collection")
            et.save()
        return et

    def test_all_strategies_resolve_correctly(self):
        rebuild_et = self._migrate_v1_to_corrupted_v2("real_rebuild")
        user_edited_et = self._migrate_v1_to_corrupted_v2("real_user_edited", post_edit=True)
        # Born V2 (no migration revision) → not_migrated → untouched.
        not_migrated_et = EventTypeFactory.create(
            value="real_not_migrated",
            schema=_corrupted_v2_collection_text(),
            version=EventType.VersionChoices.VERSION_2,
        )
        not_migrated_original = not_migrated_et.schema
        user_edited_original = user_edited_et.schema

        with connection.schema_editor() as schema_editor:
            run_repair_migration(_historical_apps(), schema_editor)

        rebuild_et.refresh_from_db()
        user_edited_et.refresh_from_db()
        not_migrated_et.refresh_from_db()

        # REBUILD_FROM_V1: re-migrated from reconstructed V1 → prefixed UI.
        rebuilt = json.loads(rebuild_et.schema)
        assert "wildlife_trophies.species" in rebuilt["ui"]["fields"]
        assert "wildlife_trophies.count" in rebuilt["ui"]["fields"]

        # SKIP_USER_EDITED and NOT_MIGRATED are left byte-for-byte intact.
        assert user_edited_et.schema == user_edited_original
        assert not_migrated_et.schema == not_migrated_original

    def test_rerun_is_idempotent(self):
        rebuild_et = self._migrate_v1_to_corrupted_v2("real_rerun")

        with connection.schema_editor() as schema_editor:
            run_repair_migration(_historical_apps(), schema_editor)
        rebuild_et.refresh_from_db()
        after_first = rebuild_et.schema

        with connection.schema_editor() as schema_editor:
            run_repair_migration(_historical_apps(), schema_editor)
        rebuild_et.refresh_from_db()

        # REBUILD_FROM_V1 is deterministic: re-running reproduces the same
        # clean V2 from the same reconstructed V1.
        assert rebuild_et.schema == after_first
