"""Tests for source_deletion helpers and the purge_observation source_observations subcommand.

Coverage:
1. delete_source_cascade removes ObservationSegments that reference the source's observations.
2. delete_source_observations removes observations + segments + LatestObservationSource
   while keeping Source / SubjectSource / SourcePlugin / group memberships.
3. purge_observation source_observations subcommand (dry-run, keep-sources, normal).
4. Batched observation and segment deletes terminate correctly across multiple batches.
5. Tenant isolation: raw SQL operates only on the current tenant's rows.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from django.contrib.gis.geos import Point

from factories import SourceFactory, SubjectSourceFactory, TenantFactory
from observations.models import (
    LatestObservationSource,
    Observation,
    ObservationSegment,
    Source,
    SubjectSource,
)
from observations.services.source_deletion import (
    delete_source_cascade,
    delete_source_observations,
)
from utils.tenant import get_tenant_settings


def _make_segment(obs1: Observation, obs2: Observation, subject) -> ObservationSegment:
    """Create an ObservationSegment linking two observations."""
    return ObservationSegment.objects.create_segment(obs1, obs2, subject)


def _make_observations(source, tenant, count: int = 2) -> list[Observation]:
    """Create ``count`` observations at evenly-spaced times and longitudes."""
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    return [
        Observation.objects.create(
            source=source,
            recorded_at=base_time + timedelta(hours=i),
            location=Point(float(i), 0.0),
            das_tenant=tenant,
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Task 1: delete_source_cascade removes ObservationSegments
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeleteSourceCascadeRemovesSegments:
    """delete_source_cascade must clean up ObservationSegments whose start_ or
    end_observation references the deleted source's observations."""

    def _run(self, source_id: str) -> tuple[int, list]:
        return delete_source_cascade(str(source_id), log_label="test_source")

    def test_removes_segments_referencing_source_observations(self, das_tenant):
        """Segments linking two observations of the same source are removed."""
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        subject = ss.subject
        obs1, obs2 = _make_observations(source, das_tenant)
        _make_segment(obs1, obs2, subject)

        assert (
            ObservationSegment.objects.filter(start_observation__source=source).count() == 1
        ), "precondition: segment exists"

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            self._run(source.id)

        assert not ObservationSegment.objects.filter(
            start_observation__source_id=source.id
        ).exists(), "segment with start_observation from source must be removed"
        assert not ObservationSegment.objects.filter(
            end_observation__source_id=source.id
        ).exists(), "segment with end_observation from source must be removed"
        assert not Observation.objects.filter(source_id=source.id).exists()
        assert not Source.objects.filter(id=source.id).exists()

    def test_removes_segments_where_only_end_observation_belongs_to_source(self, das_tenant):
        """A segment whose end_observation comes from the deleted source is also removed."""
        ss1 = SubjectSourceFactory(das_tenant=das_tenant)
        ss2 = SubjectSourceFactory(source=ss1.source, subject=ss1.subject, das_tenant=das_tenant)
        # Two distinct sources; one segment spans an obs from source_a to an obs from source_b
        source_a = ss1.source
        source_b = SourceFactory(das_tenant=das_tenant)
        subject = ss1.subject
        # obs_a at T=0, obs_b at T=1
        base_time = datetime(2024, 2, 1, tzinfo=timezone.utc)

        obs_a = Observation.objects.create(
            source=source_a,
            recorded_at=base_time,
            location=Point(0.0, 0.0),
            das_tenant=das_tenant,
        )
        obs_b = Observation.objects.create(
            source=source_b,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1.0, 0.0),
            das_tenant=das_tenant,
        )
        _make_segment(obs_a, obs_b, subject)
        assert ObservationSegment.objects.count() >= 1, "precondition: segment exists"

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            delete_source_cascade(str(source_b.id), log_label="source_b")

        # Segment that had obs_b as end_observation must be gone
        assert not ObservationSegment.objects.filter(end_observation=obs_b).exists()

    def test_also_fixes_delete_source_task_path(self, das_tenant):
        """delete_source_cascade is shared with core.tasks.delete_source_task, so
        fixing the helper fixes both code paths — no separate patch needed."""
        from django.core.cache import cache

        from core.tasks import SOURCE_DELETING_CACHE_KEY, delete_source_task

        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        subject = ss.subject
        obs1, obs2 = _make_observations(source, das_tenant)
        _make_segment(obs1, obs2, subject)

        cache.set(SOURCE_DELETING_CACHE_KEY.format(source.id), True, 60)
        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            delete_source_task(str(source.id), domain=get_tenant_settings().domain)

        assert not ObservationSegment.objects.filter(start_observation__source_id=source.id).exists()
        assert not Source.objects.filter(id=source.id).exists()


# ---------------------------------------------------------------------------
# Task 2: delete_source_observations helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeleteSourceObservations:
    """delete_source_observations removes observations, segments, and
    LatestObservationSource while keeping the Source row and related objects."""

    def _run(self, source_id) -> tuple[int, list]:
        return delete_source_observations(str(source_id), log_label="test")

    def test_removes_observations(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        _make_observations(source, das_tenant, count=3)
        assert Observation.objects.filter(source=source).count() == 3

        count, _ = self._run(source.id)

        assert count == 3
        assert not Observation.objects.filter(source=source).exists()

    def test_removes_segments(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        subject = ss.subject
        obs1, obs2 = _make_observations(source, das_tenant)
        _make_segment(obs1, obs2, subject)

        assert ObservationSegment.objects.filter(start_observation__source=source).count() == 1

        self._run(source.id)

        assert not ObservationSegment.objects.filter(start_observation__source=source).exists()
        assert not ObservationSegment.objects.filter(end_observation__source=source).exists()

    def test_removes_latest_observation_source(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        obs = _make_observations(source, das_tenant, count=1)[0]
        # Ensure a LatestObservationSource row exists (triggers may not run in tests).
        if not LatestObservationSource.objects.filter(source=source).exists():
            LatestObservationSource.objects.create(source=source, observation=obs, recorded_at=obs.recorded_at)
        assert LatestObservationSource.objects.filter(source=source).exists()

        self._run(source.id)

        assert not LatestObservationSource.objects.filter(source=source).exists()

    def test_source_row_is_preserved(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        _make_observations(source, das_tenant)

        self._run(source.id)

        assert Source.objects.filter(id=source.id).exists(), "Source row must survive"

    def test_subject_source_is_preserved(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        _make_observations(source, das_tenant)

        self._run(source.id)

        assert SubjectSource.objects.filter(id=ss.id).exists(), "SubjectSource must survive"

    def test_source_plugin_is_not_deleted(self, das_tenant):
        """delete_source_observations must not call _raw_delete on SourcePlugin.
        We wrap (not replace) _raw_delete so the real deletes still happen, and
        record the model of every queryset passed to it."""
        from observations.services.source_deletion import _raw_delete as real_raw_delete

        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        _make_observations(source, das_tenant)

        with patch("observations.services.source_deletion._raw_delete", wraps=real_raw_delete) as mock_raw:
            self._run(source.id)

        deleted_model_names = [call.args[0].model.__name__ for call in mock_raw.call_args_list]
        assert "SourcePlugin" not in deleted_model_names, "delete_source_observations must not delete SourcePlugin rows"

    def test_group_memberships_are_preserved(self, das_tenant):
        from observations.models import SourceGroup

        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        group = SourceGroup.objects.create(name="test-group", das_tenant=das_tenant)
        source.groups.add(group)
        _make_observations(source, das_tenant)

        self._run(source.id)

        assert source.groups.filter(id=group.id).exists(), "group membership must survive"

    def test_returns_correct_count_and_subject_ids(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        _make_observations(source, das_tenant, count=4)

        count, subject_ids = self._run(source.id)

        assert count == 4
        assert ss.subject_id in subject_ids

    def test_returns_zero_when_source_missing(self):
        import uuid

        count, subject_ids = delete_source_observations(str(uuid.uuid4()))

        assert count == 0
        assert subject_ids == []


# ---------------------------------------------------------------------------
# Task 3: purge_observation source_observations CLI subcommand
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestPurgeObservationSourceObservationsCommand:
    """End-to-end tests for the source_observations subcommand of purge_observation."""

    def _run_command(self, source_id, *, dry_run: bool = False, keep_sources_file: str | None = None):
        """Invoke the purge_observation management command by calling PurgeObservations directly.

        The management command requires a file-handle for pks and a live tenant
        context (TenantCommandMixin), so we call the handler class directly to
        avoid the overhead of subprocess/call_command argument parsing while
        still exercising all the business logic.
        """
        from observations.management.commands.purge_observation import PurgeObservations

        purger = PurgeObservations(dry_run=dry_run, sources_file=keep_sources_file)
        source = Source.objects.get(id=source_id)
        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            purger.remove_source_observations(source)

    def test_observations_deleted(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        _make_observations(source, das_tenant, count=3)

        self._run_command(source.id)

        assert not Observation.objects.filter(source=source).exists()
        assert Source.objects.filter(id=source.id).exists(), "Source must not be deleted"

    def test_segments_deleted(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        subject = ss.subject
        obs1, obs2 = _make_observations(source, das_tenant)
        _make_segment(obs1, obs2, subject)

        self._run_command(source.id)

        assert not ObservationSegment.objects.filter(start_observation__source=source).exists()

    def test_dry_run_deletes_nothing(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        subject = ss.subject
        obs1, obs2 = _make_observations(source, das_tenant)
        _make_segment(obs1, obs2, subject)
        obs_count_before = Observation.objects.filter(source=source).count()
        seg_count_before = ObservationSegment.objects.filter(start_observation__source=source).count()

        self._run_command(source.id, dry_run=True)

        assert Observation.objects.filter(source=source).count() == obs_count_before
        assert ObservationSegment.objects.filter(start_observation__source=source).count() == seg_count_before
        assert Source.objects.filter(id=source.id).exists()

    def test_keep_sources_skips_matching_source(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        manufacturer_id = source.manufacturer_id
        _make_observations(source, das_tenant, count=2)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
            fh.write(manufacturer_id + "\n")
            keep_file = fh.name

        self._run_command(source.id, keep_sources_file=keep_file)

        # Observations must NOT have been deleted because the source is on the keep list.
        assert Observation.objects.filter(source=source).count() == 2

    def test_source_with_null_manufacturer_id_does_not_raise(self, das_tenant):
        """Source.manufacturer_id is nullable; is_keep_source() must not crash
        with AttributeError when checking a source that has none."""
        ss = SubjectSourceFactory(das_tenant=das_tenant, source__manufacturer_id=None)
        source = ss.source
        _make_observations(source, das_tenant, count=2)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
            fh.write("some-other-manufacturer-id\n")
            keep_file = fh.name

        self._run_command(source.id, keep_sources_file=keep_file)

        assert not Observation.objects.filter(source=source).exists()

    def test_enqueues_subject_status_task(self, das_tenant):
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        _make_observations(source, das_tenant, count=2)

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async") as mock_apply:
            from observations.management.commands.purge_observation import (
                PurgeObservations,
            )

            purger = PurgeObservations(dry_run=False)
            purger.remove_source_observations(source)

        enqueued_ids = {call.kwargs["args"][0] for call in mock_apply.call_args_list}
        assert str(ss.subject_id) in enqueued_ids


# ---------------------------------------------------------------------------
# Task 4: multi-batch termination
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestBatchedDeleteTermination:
    """The observation and segment delete loops must complete across multiple
    batches when OBSERVATION_DELETE_BATCH_SIZE is smaller than the row count."""

    def test_observation_delete_spans_multiple_batches(self, das_tenant, monkeypatch):
        """With batch size 2 and 5 observations, the loop must run 3 times and
        return a total count of 5 with all rows gone."""
        monkeypatch.setattr("observations.services.source_deletion.OBSERVATION_DELETE_BATCH_SIZE", 2)
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        _make_observations(source, das_tenant, count=5)

        assert Observation.objects.filter(source=source).count() == 5, "precondition"

        count, _ = delete_source_observations(str(source.id), log_label="batch_test")

        assert count == 5, f"expected 5 deleted, got {count}"
        assert not Observation.objects.filter(source=source).exists()

    def test_segment_delete_spans_multiple_batches(self, das_tenant, monkeypatch):
        """With batch size 1 and 3 segments, the segment loop must run 3 times
        and remove all segments."""
        monkeypatch.setattr("observations.services.source_deletion.OBSERVATION_DELETE_BATCH_SIZE", 1)
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        subject = ss.subject
        # Create 4 observations, forming 3 consecutive segments.
        obs_list = _make_observations(source, das_tenant, count=4)
        for i in range(len(obs_list) - 1):
            _make_segment(obs_list[i], obs_list[i + 1], subject)

        assert ObservationSegment.objects.filter(start_observation__source=source).count() == 3, "precondition"

        delete_source_observations(str(source.id), log_label="seg_batch_test")

        assert not ObservationSegment.objects.filter(start_observation__source=source).exists()
        assert not ObservationSegment.objects.filter(end_observation__source=source).exists()
        assert not Observation.objects.filter(source=source).exists()

    def test_cascade_delete_spans_multiple_batches(self, das_tenant, monkeypatch):
        """delete_source_cascade with small batch size deletes all obs and segments."""
        monkeypatch.setattr("observations.services.source_deletion.OBSERVATION_DELETE_BATCH_SIZE", 2)
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source = ss.source
        subject = ss.subject
        obs_list = _make_observations(source, das_tenant, count=5)
        for i in range(len(obs_list) - 1):
            _make_segment(obs_list[i], obs_list[i + 1], subject)

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            count, subject_ids = delete_source_cascade(str(source.id), log_label="cascade_batch")

        assert count == 5
        assert not Observation.objects.filter(source=source).exists()
        assert not ObservationSegment.objects.filter(start_observation__source=source.id).exists()
        assert not Source.objects.filter(id=source.id).exists()
        assert ss.subject_id in subject_ids

    def test_cross_source_segment_spans_multiple_batches(self, das_tenant, monkeypatch):
        """Segments where one end belongs to a different source are still removed
        even when the batch size is 1."""
        monkeypatch.setattr("observations.services.source_deletion.OBSERVATION_DELETE_BATCH_SIZE", 1)
        ss = SubjectSourceFactory(das_tenant=das_tenant)
        source_a = ss.source
        source_b = SourceFactory(das_tenant=das_tenant)
        subject = ss.subject

        base_time = datetime(2024, 3, 1, tzinfo=timezone.utc)
        # Two observations from source_a, one from source_b; segments span across.
        obs_a1 = Observation.objects.create(
            source=source_a,
            recorded_at=base_time,
            location=Point(0.0, 0.0),
            das_tenant=das_tenant,
        )
        obs_a2 = Observation.objects.create(
            source=source_a,
            recorded_at=base_time + timedelta(hours=1),
            location=Point(1.0, 0.0),
            das_tenant=das_tenant,
        )
        obs_b = Observation.objects.create(
            source=source_b,
            recorded_at=base_time + timedelta(hours=2),
            location=Point(2.0, 0.0),
            das_tenant=das_tenant,
        )
        _make_segment(obs_a1, obs_a2, subject)
        _make_segment(obs_a2, obs_b, subject)

        assert ObservationSegment.objects.count() == 2, "precondition: 2 segments"

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            delete_source_cascade(str(source_a.id), log_label="cross_source")

        # Both segments must be gone: one was source_a/source_a, one was source_a/source_b.
        assert not ObservationSegment.objects.filter(start_observation=obs_a1).exists()
        assert not ObservationSegment.objects.filter(end_observation=obs_a2).exists()
        # source_b observation and source are untouched.
        assert Observation.objects.filter(id=obs_b.id).exists()
        assert Source.objects.filter(id=source_b.id).exists()


# ---------------------------------------------------------------------------
# Task 5: tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTenantIsolation:
    """The raw SQL deletes must be scoped to the current tenant's rows only."""

    def test_observations_of_other_tenant_are_not_deleted(self, monkeypatch):
        """Creating two tenants with one source each; deleting source_a's observations
        must leave source_b's observations intact."""
        from django_multitenant.utils import set_current_tenant

        tenant_a = TenantFactory()
        tenant_b = TenantFactory()

        # Bootstrap source/observations for each tenant.
        set_current_tenant(tenant_a)
        ss_a = SubjectSourceFactory(das_tenant=tenant_a)
        source_a = ss_a.source
        obs_a = _make_observations(source_a, tenant_a, count=3)

        set_current_tenant(tenant_b)
        ss_b = SubjectSourceFactory(das_tenant=tenant_b)
        source_b = ss_b.source
        obs_b = _make_observations(source_b, tenant_b, count=3)

        # Operate as tenant_a.
        set_current_tenant(tenant_a)
        # Patch multitenant thread-locals so the ORM filter also works.
        import django_multitenant.utils as mt_utils

        mt_utils._thread_locals
        mt_utils._context

        try:
            from unittest.mock import MagicMock

            tl = MagicMock()
            tl.tenant = tenant_a
            monkeypatch.setattr(mt_utils, "_thread_locals", tl)
            monkeypatch.setattr(mt_utils, "_context", tl)

            delete_source_observations(str(source_a.id), log_label="isolation_test")

            assert not Observation.objects.filter(source=source_a).exists(), "tenant_a observations must be deleted"

            # Verify tenant_b rows survive by querying without tenant filter.
            tenant_b_obs_count = Observation.objects.filter(das_tenant=tenant_b, source=source_b).count()
            assert tenant_b_obs_count == 3, f"tenant_b's observations must not be touched; got {tenant_b_obs_count}"
        finally:
            set_current_tenant(None)

    def test_raises_when_no_tenant_in_context(self):
        """_delete_observations_and_segments must raise RuntimeError when no
        tenant is set, preventing cross-tenant deletes."""
        import uuid

        from django_multitenant.utils import get_current_tenant, set_current_tenant

        # Temporarily clear the tenant so get_current_tenant() returns None.
        previous = get_current_tenant()
        set_current_tenant(None)
        try:
            from observations.services.source_deletion import (
                _delete_observations_and_segments,
            )

            with pytest.raises(RuntimeError, match="without a tenant context"):
                _delete_observations_and_segments(str(uuid.uuid4()), "no-tenant-test")
        finally:
            set_current_tenant(previous)
