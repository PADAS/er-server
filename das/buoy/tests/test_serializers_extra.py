import json
from datetime import timedelta

import pytest

from django.contrib.gis.geos import Point
from django.utils import timezone

from buoy.serializers.gear import (
    GearCreateSerializer,
    GearDeviceCreateSerializer,
    GearSerializer,
    GeoLocationSerializer,
)
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
)


@pytest.mark.django_db
def test_geo_location_serializer_bounds():
    # Valid coordinates
    s = GeoLocationSerializer(data={"latitude": 0.0, "longitude": 0.0})
    assert s.is_valid(), s.errors

    # Invalid latitude
    s = GeoLocationSerializer(data={"latitude": 91.0, "longitude": 0.0})
    assert not s.is_valid()
    assert "Latitude must be between -90 and 90 degrees" in str(s.errors)

    # Invalid longitude
    s = GeoLocationSerializer(data={"latitude": 0.0, "longitude": 181.0})
    assert not s.is_valid()
    assert "Longitude must be between -180 and 180 degrees" in str(s.errors)


@pytest.mark.django_db
def test_gear_device_create_serializer_date_validations():
    now = timezone.now()
    future = now + timedelta(days=1)

    payload = {
        "mfr_device_id": "dev1",
        "mfr_id": "mfr",
        "last_deployed": future.isoformat(),
        "last_updated": future.isoformat(),
        "device_status": "deployed",
        "location": {"latitude": 0.0, "longitude": 0.0},
    }

    s = GearDeviceCreateSerializer(data=payload)
    assert not s.is_valid()
    # Should complain about future dates
    assert "cannot be in the future" in json.dumps(s.errors)

    # Last updated before deploy
    past = now - timedelta(days=2)
    payload = {
        "mfr_device_id": "dev1",
        "mfr_id": "mfr",
        "last_deployed": now.isoformat(),
        "last_updated": past.isoformat(),
        "device_status": "deployed",
        "location": {"latitude": 0.0, "longitude": 0.0},
    }
    s = GearDeviceCreateSerializer(data=payload)
    assert not s.is_valid()
    assert "Last updated date cannot be before deployment date" in json.dumps(s.errors)


@pytest.mark.django_db
def test_gear_create_devices_in_set_and_haul_validation():
    now = timezone.now()
    # devices_in_set mismatch
    payload = {
        "owner_id": "owner123",
        "deployment_type": "single",
        "initial_deployment_date": now.isoformat(),
        "devices_in_set": 2,
        "devices": [
            {
                "mfr_device_id": "mfr1",
                "mfr_id": "mfr",
                "last_deployed": now.isoformat(),
                "last_updated": now.isoformat(),
                "device_status": "deployed",
                "location": {"latitude": 0.0, "longitude": 0.0},
            }
        ],
    }
    s = GearCreateSerializer(data=payload, context={"user_id": 1})
    assert not s.is_valid()
    assert "devices_in_set" in json.dumps(s.errors)

    # Hauling a device that's not deployed should error
    payload = {
        "owner_id": "owner123",
        "deployment_type": "single",
        "initial_deployment_date": now.isoformat(),
        "devices": [
            {
                "mfr_device_id": "mfr-not-exist",
                "mfr_id": "mfr",
                "last_deployed": now.isoformat(),
                "last_updated": now.isoformat(),
                "device_status": "hauled",
                "location": {"latitude": 0.0, "longitude": 0.0},
            }
        ],
    }
    s = GearCreateSerializer(data=payload, context={"user_id": 1})
    assert not s.is_valid()
    assert "not deployed" in json.dumps(s.errors)


@pytest.mark.django_db
def test_get_gearset_id_finds_existing_subject():
    # Create subject and sources that match device ids
    subject = Subject.objects.create(name="SET123", subject_subtype=None, is_active=True)
    provider = SourceProvider.objects.create(display_name="P", provider_key="pkey")
    src1 = Source.objects.create(manufacturer_id="A", provider=provider)
    src2 = Source.objects.create(manufacturer_id="B", provider=provider)
    from psycopg2.extras import DateTimeTZRange

    now = timezone.now()
    rng = DateTimeTZRange(now - timedelta(days=1), None)
    SubjectSource.objects.create(subject=subject, source=src1, assigned_range=rng)
    SubjectSource.objects.create(subject=subject, source=src2, assigned_range=rng)

    serializer = GearCreateSerializer()
    set_id = serializer._get_gearset_id({}, [{"mfr_device_id": "A"}, {"mfr_device_id": "B"}])
    assert set_id == str(subject.name)


@pytest.mark.django_db
def test_gear_serializer_devices_and_manufacturer():
    # Ensure GearSerializer returns devices and prefers additional manufacturer
    subject = Subject.objects.create(name="S1", subject_subtype=None, is_active=True)
    subject.additional = {"manufacturer": "acme"}
    subject.save()
    provider = SourceProvider.objects.create(display_name="P", provider_key="gundi_acme_1234")
    src = Source.objects.create(manufacturer_id="dev1", provider=provider)
    now = timezone.now()
    from psycopg2.extras import DateTimeTZRange

    rng = DateTimeTZRange(now - timedelta(days=1), None)
    ss = SubjectSource.objects.create(subject=subject, source=src, assigned_range=rng)

    # Create an observation for source to provide location
    point = Point(-24.43, 31.19)
    Observation.objects.create(recorded_at=now, location=point, source=src)

    s = GearSerializer(ss)
    data = s.data
    assert data["manufacturer"] == "acme"
    assert isinstance(data["devices"], list)
    assert len(data["devices"]) >= 1
    dev = data["devices"][0]
    assert dev["device_id"] == "dev1"
    assert dev["location"]["latitude"] == pytest.approx(31.19)
