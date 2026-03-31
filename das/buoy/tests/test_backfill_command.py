from __future__ import annotations

from io import StringIO

import pytest
from psycopg2.extras import DateTimeTZRange

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.utils import timezone

from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from factories import SubjectTypeFactory
from observations.models import (
    LatestObservationSource,
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
    SubjectSubType,
)


@pytest.fixture()
def gear_subjects_for_backfill():
    """Create gear subjects with SubjectSources that need location backfill."""
    subject_type = SubjectTypeFactory(value="gear")
    subject_subtype = SubjectSubType.objects.create(
        value=BUOY_GEAR_SUBJECT_SUBTYPE, display="Ropeless Buoy Gearset", subject_type=subject_type
    )
    provider = SourceProvider.objects.create(display_name="Backfill Provider", provider_key="backfill_provider")

    now = timezone.now()
    location = Point(-24.43071, 31.19239)

    # Subject with a source that has an observation (should be updated)
    subject1 = Subject.objects.create(name="Backfill_Gear_1", subject_subtype=subject_subtype, is_active=True)
    source1 = Source.objects.create(manufacturer_id="backfill_dev_001", provider=provider)
    ss1 = SubjectSource.objects.create(
        subject=subject1,
        source=source1,
        assigned_range=DateTimeTZRange(now, None),
        location=None,
    )
    obs1 = Observation.objects.create(recorded_at=now, location=location, source=source1)
    LatestObservationSource.objects.update_or_create(source=source1, defaults={"observation": obs1})

    # Subject with a source that has no observation (should be skipped)
    subject2 = Subject.objects.create(name="Backfill_Gear_2", subject_subtype=subject_subtype, is_active=True)
    source2 = Source.objects.create(manufacturer_id="backfill_dev_002", provider=provider)
    ss2 = SubjectSource.objects.create(
        subject=subject2,
        source=source2,
        assigned_range=DateTimeTZRange(now, None),
        location=None,
    )

    # Subject with a source that has observation at (0,0) (should be skipped as empty point)
    subject3 = Subject.objects.create(name="Backfill_Gear_3", subject_subtype=subject_subtype, is_active=True)
    source3 = Source.objects.create(manufacturer_id="backfill_dev_003", provider=provider)
    ss3 = SubjectSource.objects.create(
        subject=subject3,
        source=source3,
        assigned_range=DateTimeTZRange(now, None),
        location=None,
    )
    obs3 = Observation.objects.create(recorded_at=now, location=Point(0, 0), source=source3)
    LatestObservationSource.objects.update_or_create(source=source3, defaults={"observation": obs3})

    # Inactive subject with a valid observation (should be excluded from backfill)
    subject4 = Subject.objects.create(name="Backfill_Gear_4_Inactive", subject_subtype=subject_subtype, is_active=False)
    source4 = Source.objects.create(manufacturer_id="backfill_dev_004", provider=provider)
    ss4 = SubjectSource.objects.create(
        subject=subject4,
        source=source4,
        assigned_range=DateTimeTZRange(now, None),
        location=None,
    )
    obs4 = Observation.objects.create(recorded_at=now, location=location, source=source4)
    LatestObservationSource.objects.update_or_create(source=source4, defaults={"observation": obs4})

    return ss1, ss2, ss3, ss4, location


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestBackfillGearSubjectSourceLocation:
    def test_backfills_location_from_latest_observation(self, gear_subjects_for_backfill):
        ss1, ss2, ss3, ss4, expected_location = gear_subjects_for_backfill

        out = StringIO()
        call_command("backfill_gear_subjectsource_location", stdout=out)

        ss1.refresh_from_db()
        ss2.refresh_from_db()
        ss3.refresh_from_db()
        ss4.refresh_from_db()

        assert ss1.location is not None
        assert ss1.location.x == expected_location.x
        assert ss1.location.y == expected_location.y

        # No observation — location stays None
        assert ss2.location is None

        # Empty point (0,0) — location stays None
        assert ss3.location is None

        # Inactive subject — excluded from backfill, location stays None
        assert ss4.location is None

        output = out.getvalue()
        assert "Updated: 1" in output
        assert "skipped (no observation): 1" in output
        assert "skipped (empty point / 0,0): 1" in output

    def test_dry_run_does_not_write(self, gear_subjects_for_backfill):
        ss1, _, _, _, _ = gear_subjects_for_backfill

        out = StringIO()
        call_command("backfill_gear_subjectsource_location", "--dry-run", stdout=out)

        ss1.refresh_from_db()
        assert ss1.location is None

        assert "DRY RUN" in out.getvalue()
