from datetime import timedelta
from unittest.mock import patch

import pytest
from psycopg2.extras import DateTimeTZRange

from django.contrib.gis.geos import Point
from django.utils import timezone

from observations.management.commands.trim_observations import Command
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
)


@pytest.mark.django_db
class TestTrimObservationsCommand:
    def test_trim_by_source_id_deletes_only_older_rows(self, das_tenant_monkeypatch):
        provider = SourceProvider.objects.create(
            provider_key="test",
            display_name="test",
            das_tenant=das_tenant_monkeypatch,
        )
        source = Source.objects.create(
            provider=provider,
            manufacturer_id="m1",
            source_type="gps-radio",
            model_name="x",
            das_tenant=das_tenant_monkeypatch,
        )
        other_source = Source.objects.create(
            provider=provider,
            manufacturer_id="m2",
            source_type="gps-radio",
            model_name="x",
            das_tenant=das_tenant_monkeypatch,
        )

        before = timezone.now()
        old_time = before - timedelta(days=2)
        new_time = before + timedelta(seconds=10)

        old_obs = Observation.objects.create(
            source=source,
            recorded_at=old_time,
            location=Point(0, 0),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )
        Observation.objects.create(
            source=source,
            recorded_at=new_time,
            location=Point(0, 0),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )
        Observation.objects.create(
            source=other_source,
            recorded_at=old_time,
            location=Point(0, 0),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async") as apply_async_mock:
            Command().handle(before=before.isoformat(), source_id=str(source.id), dry_run=False, batch_size=1000)
            apply_async_mock.assert_not_called()

        assert not Observation.objects.filter(id=old_obs.id).exists()
        assert Observation.objects.filter(source=source).count() == 1
        assert Observation.objects.filter(source=other_source).count() == 1

    def test_trim_by_subject_id_respects_assignment_ranges(self, das_tenant_monkeypatch):
        provider = SourceProvider.objects.create(
            provider_key="test",
            display_name="test",
            das_tenant=das_tenant_monkeypatch,
        )
        source = Source.objects.create(
            provider=provider,
            manufacturer_id="m1",
            source_type="gps-radio",
            model_name="x",
            das_tenant=das_tenant_monkeypatch,
        )
        subject = Subject.objects.create(name="s1", subject_subtype_id="unassigned", das_tenant=das_tenant_monkeypatch)

        # Assignment only covers a small window.
        base = timezone.now()
        assignment_start = base - timedelta(days=10)
        assignment_end = base - timedelta(days=5)
        SubjectSource.objects.create(
            subject=subject,
            source=source,
            assigned_range=DateTimeTZRange(lower=assignment_start, upper=assignment_end),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )

        # Observation within assignment range (old) => should be deleted.
        in_range_old = assignment_start + timedelta(hours=1)
        in_range_obs = Observation.objects.create(
            source=source,
            recorded_at=in_range_old,
            location=Point(0, 0),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )

        # Observation outside assignment range (also old) => should NOT be deleted by subject trimming.
        out_of_range_old = assignment_end + timedelta(days=1)
        out_of_range_obs = Observation.objects.create(
            source=source,
            recorded_at=out_of_range_old,
            location=Point(0, 0),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )

        before = base
        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async") as apply_async_mock:
            Command().handle(before=before.isoformat(), subject_id=str(subject.id), dry_run=False, batch_size=1000)
            apply_async_mock.assert_called_once()
            assert apply_async_mock.call_args.kwargs == {"args": (str(subject.id),)}

        assert not Observation.objects.filter(id=in_range_obs.id).exists()
        assert Observation.objects.filter(id=out_of_range_obs.id).exists()

    def test_trim_by_source_id_only_reconciles_subjects_in_trimmed_window(self, das_tenant_monkeypatch):
        # When trimming a source, only subjects whose SubjectSource overlapped the
        # trimmed window (-inf, before) should be enqueued for SubjectStatus
        # reconciliation. Subjects assigned to the same source AFTER `before` had
        # nothing trimmed and must not be enqueued.
        provider = SourceProvider.objects.create(
            provider_key="test", display_name="test", das_tenant=das_tenant_monkeypatch
        )
        source = Source.objects.create(
            provider=provider,
            manufacturer_id="m1",
            source_type="gps-radio",
            model_name="x",
            das_tenant=das_tenant_monkeypatch,
        )
        subject_in_window = Subject.objects.create(
            name="in_window", subject_subtype_id="unassigned", das_tenant=das_tenant_monkeypatch
        )
        subject_after_window = Subject.objects.create(
            name="after_window", subject_subtype_id="unassigned", das_tenant=das_tenant_monkeypatch
        )

        base = timezone.now()
        before = base
        # subject_in_window had the source from base-10d to base-5d (entirely before `before`).
        SubjectSource.objects.create(
            subject=subject_in_window,
            source=source,
            assigned_range=DateTimeTZRange(lower=base - timedelta(days=10), upper=base - timedelta(days=5)),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )
        # subject_after_window has the source from base+1d onward (entirely after `before`).
        SubjectSource.objects.create(
            subject=subject_after_window,
            source=source,
            assigned_range=DateTimeTZRange(lower=base + timedelta(days=1), upper=None),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )

        # One old observation to give the trim something to do.
        Observation.objects.create(
            source=source,
            recorded_at=base - timedelta(days=7),
            location=Point(0, 0),
            additional={},
            das_tenant=das_tenant_monkeypatch,
        )

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async") as apply_async_mock:
            Command().handle(before=before.isoformat(), source_id=str(source.id), dry_run=False, batch_size=1000)

        enqueued = {call.kwargs["args"][0] for call in apply_async_mock.call_args_list}
        assert enqueued == {str(subject_in_window.id)}, (
            "must enqueue only subjects whose assignment overlapped the trimmed window — "
            "fanning out to former/future assignees creates noise tasks"
        )
