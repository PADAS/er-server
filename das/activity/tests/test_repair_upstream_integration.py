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
* the ``repair_v2_collection_schemas`` management command drives all of the
  above through the live ORM + real upstream, applying the right action per
  strategy, and creates revision rows for applied repairs (audit trail);
* ``--dry-run`` reports what would change without writing anything.

If the upstream contract changes shape (``RepairChange`` fields, the
``LogCollector`` error dict, the prefixing convention) these tests fail
loudly rather than silently passing on stale mocks. See
``docs/architecture/v2-schema-repair-upstream-contract.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import StringIO
from typing import Any
from unittest import mock
from uuid import uuid4

import pytest

from django.core.exceptions import ValidationError
from django.core.management import call_command

from activity.management.commands import repair_v2_collection_schemas as repair_cmd
from activity.models import EventType
from activity.schemas.migration.repair import RepairClassification, RepairStrategy
from activity.schemas.migration.repair_apply import (
    APPLIED_REBUILT_FROM_V1,
    APPLIED_RECONSTRUCTED_FROM_JSON,
    SKIPPED_ALREADY_CORRECT,
    SKIPPED_NEEDS_REVIEW,
    RepairOutcome,
    attempt_repair,
)
from activity.schemas.ops.revision_history import EventTypeRevisionHistory
from factories import EventTypeFactory
from revision.manager import ACTION_ADDED, ACTION_UPDATED

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


# ── Management command through live ORM + real upstream ───────────────────


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestRepairCommandRealUpstream:
    """Run ``repair_v2_collection_schemas`` with no mocking — real revisions,
    real upstream tool, live ORM."""

    def _run(self, *args, tenant_domain: str | None = None, **kwargs) -> tuple[str, str]:
        """Call the command and return (stdout, stderr) as strings."""
        out = StringIO()
        err = StringIO()
        call_command(
            "repair_v2_collection_schemas",
            *args,
            tenant_domain=tenant_domain,
            stdout=out,
            stderr=err,
            **kwargs,
        )
        return out.getvalue(), err.getvalue()

    def _migrate_v1_to_corrupted_v2(self, value: str, *, post_edit: bool = False) -> EventType:
        """Simulate a V1→V2 migration by saving through the live ORM so the
        revision trail is recorded correctly (fetch() uses the live descriptor)."""
        et = EventTypeFactory.create(
            value=value,
            schema=_v1_collection_text(),
            version=EventType.VersionChoices.VERSION_1,
        )
        # Simulate the migration: schema + version both change simultaneously.
        et.schema = _corrupted_v2_collection_text()
        et.version = EventType.VersionChoices.VERSION_2
        et.save()
        if post_edit:
            # A post-migration user edit — must be respected (skipped).
            et.schema = _corrupted_v2_collection_text("user_added_collection")
            et.save()
        return et

    def test_rebuild_from_v1_strategy_repairs_schema(self, das_tenant):
        """REBUILD_FROM_V1: a V1 snapshot in history → re-migrated to clean V2."""
        et = self._migrate_v1_to_corrupted_v2("cmd_rebuild")

        self._run("--all", tenant_domain=das_tenant.domain)

        et.refresh_from_db()
        rebuilt = json.loads(et.schema)
        assert "wildlife_trophies.species" in rebuilt["ui"]["fields"]
        assert "wildlife_trophies.count" in rebuilt["ui"]["fields"]

    def test_skip_user_edited_leaves_schema_untouched(self, das_tenant):
        """SKIP_USER_EDITED: post-migration edits must not be overwritten."""
        et = self._migrate_v1_to_corrupted_v2("cmd_user_edited", post_edit=True)
        original_schema = et.schema

        self._run("--all", tenant_domain=das_tenant.domain)

        et.refresh_from_db()
        assert et.schema == original_schema

    def test_not_migrated_leaves_schema_untouched(self, das_tenant):
        """NOT_MIGRATED: EventType born V2 (no migration revision) → untouched."""
        et = EventTypeFactory.create(
            value="cmd_not_migrated",
            schema=_corrupted_v2_collection_text(),
            version=EventType.VersionChoices.VERSION_2,
        )
        original_schema = et.schema

        self._run("--all", tenant_domain=das_tenant.domain)

        et.refresh_from_db()
        assert et.schema == original_schema

    def test_needs_review_reported_on_stderr(self, das_tenant):
        """A SKIPPED_NEEDS_REVIEW outcome is surfaced on stderr so operators can
        build a manual-review queue.

        The upstream *classification* of ambiguous corruption is covered by
        ``TestReconstructFromJsonRealUpstream.test_diagnostics_only_schema_returns_skipped_needs_review``.
        Here we stub ``attempt_repair`` so the command's *reporting* of a
        needs-review outcome is asserted deterministically. (The previous version
        accepted either needs_review or already_correct and never asserted the
        stderr line, so it did not actually test the reporting path.)
        """
        et = self._migrate_v1_to_corrupted_v2("cmd_needs_review")
        original_schema = et.schema

        needs_review = RepairOutcome(
            classification=RepairClassification(
                event_type_value="cmd_needs_review",
                event_type_id=str(et.id),
                strategy=RepairStrategy.RECONSTRUCT_FROM_JSON,
            ),
            action=SKIPPED_NEEDS_REVIEW,
            metadata={
                "upstream_changes": 1,
                "upstream_change_summary": [
                    {"action": "ambiguous_collision_kept", "field_path": "trophies.num", "details": "kept"}
                ],
            },
        )

        with mock.patch.object(repair_cmd, "attempt_repair", return_value=needs_review):
            _, stderr = self._run("--all", tenant_domain=das_tenant.domain)

        assert "cmd_needs_review" in stderr
        assert "needs manual review" in stderr

        # needs_review is a skip: the stored schema must be left untouched.
        et.refresh_from_db()
        assert et.schema == original_schema

    def test_error_action_is_reported_and_run_continues(self, das_tenant):
        """A row that produces an error_* action is surfaced on stderr and the
        run still repairs the other rows.

        ``et_bad`` migrates from a pre-migration V1 snapshot that is not valid
        JSON, so it classifies as REBUILD_FROM_V1 and then fails to parse the
        reconstructed V1 — a deterministic error outcome. (The previous version
        put ``not-json{{{`` in the *current* schema, which classifies as a benign
        ``skip_user_edited`` and never exercised any error path.)
        """
        et_good = self._migrate_v1_to_corrupted_v2("cmd_error_good")

        et_bad = EventTypeFactory.create(
            value="cmd_error_bad",
            schema="not valid json",
            version=EventType.VersionChoices.VERSION_1,
        )
        # Migrate to a V2-shaped current schema so a migration revision exists;
        # the reconstructed V1 ("not valid json") then fails to parse on rebuild.
        et_bad.schema = _corrupted_v2_collection_text()
        et_bad.version = EventType.VersionChoices.VERSION_2
        et_bad.save()

        # The run must not raise even with a failing row present.
        stdout, stderr = self._run("--all", tenant_domain=das_tenant.domain)

        # The good event type is still repaired despite the bad row erroring.
        et_good.refresh_from_db()
        assert "wildlife_trophies.species" in json.loads(et_good.schema)["ui"]["fields"]

        # The failure is surfaced on stderr (not silently swallowed) and the run
        # completes with a Done summary.
        assert "cmd_error_bad" in stderr
        assert "error" in stderr.lower()
        assert "Done." in stdout

    def test_validation_error_on_save_is_bucketed_separately_and_run_continues(self, das_tenant):
        """A row that fails model validation on save is counted in the distinct
        ``error_validation`` bucket (not the generic ``error_unexpected`` bucket),
        and the run still repairs the other rows.

        ``EventType.save()`` runs ``full_clean()`` on every save — including the
        partial ``update_fields`` save this command issues — so a legacy/damaged
        row with an unrelated invalid field raises ``ValidationError``. That must
        be surfaced as its own outcome, not swallowed into the catch-all handler.
        """
        et_good = self._migrate_v1_to_corrupted_v2("cmd_validation_good")
        et_bad = self._migrate_v1_to_corrupted_v2("cmd_validation_bad")

        real_save = EventType.save

        def failing_save(self, *args, **kwargs):
            # Only the damaged row fails validation on save; the good row saves
            # normally so we can prove the run continued past the failure.
            if self.value == "cmd_validation_bad":
                raise ValidationError({"icon": "Ensure this value has at most 255 characters."})
            return real_save(self, *args, **kwargs)

        with mock.patch.object(EventType, "save", autospec=True, side_effect=failing_save):
            stdout, stderr = self._run("--all", tenant_domain=das_tenant.domain)

        # The bad row is reported as a validation error (its own message), not a
        # generic unexpected error.
        assert "cmd_validation_bad" in stderr
        assert "validation error" in stderr.lower()

        # The distinct bucket appears in the summary; the generic bucket does not.
        assert "error_validation" in stdout
        assert "error_unexpected" not in stdout

        # The run continued: the good row was still repaired.
        et_good.refresh_from_db()
        assert "wildlife_trophies.species" in json.loads(et_good.schema)["ui"]["fields"]

        # The damaged row's schema was left untouched (save was rejected).
        et_bad.refresh_from_db()
        assert et_bad.schema == _corrupted_v2_collection_text()

    def test_dry_run_does_not_write_to_db(self, das_tenant):
        """--dry-run must report what would change but leave the DB untouched."""
        et = self._migrate_v1_to_corrupted_v2("cmd_dry_run_repair")
        original_schema = et.schema

        stdout, _ = self._run("--all", "--dry-run", tenant_domain=das_tenant.domain)

        et.refresh_from_db()
        assert et.schema == original_schema, "Dry-run must not write schema changes to the database"
        assert (
            "would apply" in stdout.lower() or "dry" in stdout.lower() or "Done." in stdout
        ), f"Expected dry-run indicator in output but got: {stdout!r}"

    def test_applied_repair_creates_revision_row(self, das_tenant):
        """Saving through the live model fires RevisionMixin — a revision row
        must exist after the repair (audit trail)."""
        et = self._migrate_v1_to_corrupted_v2("cmd_revision_audit")
        revision_count_before = et.revision.count()

        self._run("--all", tenant_domain=das_tenant.domain)

        et.refresh_from_db()
        revision_count_after = et.revision.count()
        assert (
            revision_count_after > revision_count_before
        ), f"Expected a new revision row after repair but count stayed at {revision_count_before}"

    def test_rerun_is_idempotent(self, das_tenant):
        """Running the command twice produces the same schema on the second pass."""
        et = self._migrate_v1_to_corrupted_v2("cmd_idempotent")

        self._run("--all", tenant_domain=das_tenant.domain)
        et.refresh_from_db()
        after_first = et.schema

        self._run("--all", tenant_domain=das_tenant.domain)
        et.refresh_from_db()

        # The first repair appended a schema-only revision (the live save fires
        # RevisionMixin), so the second pass classifies the EventType as
        # skip_user_edited and leaves it untouched — the stored schema is already
        # correct, so it stays byte-for-byte identical.
        assert et.schema == after_first

    def test_explicit_values_filter_targets_only_named_types(self, das_tenant):
        """Passing explicit values must process only the named event types."""
        et_target = self._migrate_v1_to_corrupted_v2("cmd_explicit_target_repair")
        et_other = self._migrate_v1_to_corrupted_v2("cmd_explicit_other_repair")
        other_original = et_other.schema

        self._run("cmd_explicit_target_repair", tenant_domain=das_tenant.domain)

        et_target.refresh_from_db()
        et_other.refresh_from_db()

        rebuilt = json.loads(et_target.schema)
        assert "wildlife_trophies.species" in rebuilt["ui"]["fields"], "Named event type should have been repaired"
        assert et_other.schema == other_original, "Non-named event type must not be modified"

    def test_no_values_and_no_all_raises_command_error(self, das_tenant):
        """Passing neither values nor --all must raise CommandError."""
        from django.core.management import CommandError as DjangoCommandError

        with pytest.raises((DjangoCommandError, SystemExit)):
            self._run(tenant_domain=das_tenant.domain)

    def test_values_and_all_together_raises_command_error(self, das_tenant):
        """Passing both explicit values and --all must raise CommandError."""
        from django.core.management import CommandError as DjangoCommandError

        with pytest.raises((DjangoCommandError, SystemExit)):
            self._run("some_value", "--all", tenant_domain=das_tenant.domain)
