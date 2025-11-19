import json
from datetime import timedelta

import pytest
from dateutil import parser as date_parser
from psycopg2.extras import DateTimeTZRange

from django.contrib.gis.geos import Point
from django.utils import timezone

from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from buoy.serializers import GearCreateSerializer, GearSerializer
from buoy.serializers.gear import GearDeviceCreateSerializer, GeoLocationSerializer
from buoy.services.buoy_service import BuoyService
from core.tests import BaseAPITest
from factories import SubjectTypeFactory
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
    SubjectSubType,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearSerializer:
    def test_with_trawl_gear_subject(self, gear_subjectsource):
        gear_subjectsource.subject.is_active = True
        gear_subjectsource.save()

        subject = gear_subjectsource.subject
        provider = gear_subjectsource.source.provider
        provider.save()
        now = timezone.now()

        # Create a second source and SubjectSource for the same subject to make it a trawl
        source2 = Source.objects.create(manufacturer_id="mfr_device_002", provider=provider)

        # Create observations for both sources
        location1 = Point(-24.43071, 31.19239)
        location2 = Point(-24.44071, 31.20239)

        Observation.objects.create(recorded_at=now, location=location1, source=gear_subjectsource.source)
        Observation.objects.create(recorded_at=now, location=location2, source=source2)

        # Create time range for deployment
        time_range = DateTimeTZRange(now, None)

        # Update existing SubjectSource with time range
        gear_subjectsource.assigned_range = time_range
        gear_subjectsource.save()

        # Create second SubjectSource
        SubjectSource.objects.create(subject=subject, source=source2, assigned_range=time_range)

        # Set display_id in subject additional
        subject.additional = {"display_id": "Test_Gear_1"}
        subject.save()

        serialized_gear = GearSerializer(gear_subjectsource).data

        assert serialized_gear["id"] == str(subject.id)
        assert serialized_gear["display_id"] == "Test_Gear_1"
        assert serialized_gear["status"] == "deployed"
        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] == "trawl"
        assert len(serialized_gear["devices"]) == 2

        # Check device structure
        devices = serialized_gear["devices"]
        device_ids = [device["device_id"] for device in devices]
        assert str(gear_subjectsource.source.id) in device_ids
        assert str(source2.id) in device_ids

        # Test hauled status
        subject.is_active = False
        subject.save()
        serialized_gear = GearSerializer(gear_subjectsource).data
        assert serialized_gear["status"] == "hauled"

    def test_with_single_gear_subject(self, gear_subjectsource):
        gear_subjectsource.subject.is_active = True
        gear_subjectsource.save()

        subject = gear_subjectsource.subject
        source = gear_subjectsource.source
        provider = source.provider
        provider.save()
        now = timezone.now()

        # Create observation for the source
        location = Point(-24.43071, 31.19239)

        Observation.objects.create(recorded_at=now, location=location, source=source)

        # Create time range for deployment
        time_range = DateTimeTZRange(now, None)

        # Update SubjectSource with time range
        gear_subjectsource.assigned_range = time_range
        gear_subjectsource.save()

        # Set display_id in subject additional
        subject.additional = {"display_id": "Test_Gear_Single"}
        subject.save()

        serialized_gear = GearSerializer(gear_subjectsource).data

        assert serialized_gear["id"] == str(subject.id)
        assert serialized_gear["display_id"] == "Test_Gear_Single"
        assert serialized_gear["status"] == "deployed"
        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] == "single"
        assert len(serialized_gear["devices"]) == 1

        # Check device structure
        device = serialized_gear["devices"][0]
        assert device["device_id"] == str(source.id)
        assert device["mfr_device_id"] == source.manufacturer_id

        # Test hauled status
        subject.is_active = False
        subject.save()
        serialized_gear = GearSerializer(gear_subjectsource).data
        assert serialized_gear["status"] == "hauled"

    def test_with_ropeless_buoy_gearset_subject(self):
        """Test serialization of ropeless_buoy_gearset subject with multiple related sources."""
        # Arrange
        # Create a subject subtype for ropeless_buoy_gearset
        subject_type = SubjectTypeFactory(value="gear")
        subject_subtype = SubjectSubType.objects.create(
            value=BUOY_GEAR_SUBJECT_SUBTYPE, display="Ropeless Buoy Gearset", subject_type=subject_type
        )

        # Create main subject (gearset)
        subject = Subject.objects.create(name="Test_Gearset_1", subject_subtype=subject_subtype, is_active=True)

        # Create two sources (devices) that belong to this gearset
        provider = SourceProvider.objects.create(display_name="Test Provider", provider_key="test_provider")

        source1 = Source.objects.create(
            manufacturer_id="mfr_device_001",
            provider=provider,
            additional={"last_deployed": "2024-10-16T11:08:17-08:00"},
        )

        source2 = Source.objects.create(
            manufacturer_id="mfr_device_002",
            provider=provider,
            additional={"last_deployed": "2024-10-16T12:15:22-08:00"},
        )

        # Create observations for both sources
        now = timezone.now()
        location1 = Point(-24.43071, 31.19239)
        location2 = Point(-24.44071, 31.20239)

        Observation.objects.create(recorded_at=now, location=location1, source=source1)

        Observation.objects.create(recorded_at=now, location=location2, source=source2)

        # Create SubjectSource relationships with assigned_range covering current time
        from psycopg2.extras import DateTimeTZRange

        # Create a time range that includes 'now'
        deployment_time = now
        time_range = DateTimeTZRange(deployment_time, None)  # Open-ended range starting from deployment_time

        subject_source1 = SubjectSource.objects.create(subject=subject, source=source1, assigned_range=time_range)

        subject_source2 = SubjectSource.objects.create(subject=subject, source=source2, assigned_range=time_range)

        # Act
        serialized_gear = GearSerializer(subject_source1).data

        # Assert
        assert serialized_gear["id"] == str(subject.id)
        assert serialized_gear["display_id"] == subject.name
        assert serialized_gear["status"] == "deployed"
        assert "last_updated" in serialized_gear  # Just check it exists, timezone formatting may vary
        assert serialized_gear["type"] == "trawl"  # Should be trawl since > 1 device
        assert "devices" in serialized_gear
        assert len(serialized_gear["devices"]) == 2

        # Check device structure
        devices = serialized_gear["devices"]
        device_ids = [device["device_id"] for device in devices]
        assert str(source1.id) in device_ids
        assert str(source2.id) in device_ids

        # Check first device
        device1 = next(d for d in devices if d["device_id"] == str(source1.id))
        assert device1["label"] == "a"  # First device should get label 'a'
        assert device1["mfr_device_id"] == "mfr_device_001"
        assert "location" in device1
        assert device1["location"]["latitude"] == 31.19239
        assert device1["location"]["longitude"] == -24.43071
        assert "last_deployed" in device1  # Check it exists (datetime object from assigned_range.lower)

        # Check second device
        device2 = next(d for d in devices if d["device_id"] == str(source2.id))
        assert device2["label"] == "b"  # Second device should get label 'b'
        assert device2["mfr_device_id"] == "mfr_device_002"
        assert "location" in device2
        assert device2["location"]["latitude"] == 31.20239
        assert device2["location"]["longitude"] == -24.44071
        assert "last_deployed" in device2  # Check it exists (datetime object from assigned_range.lower)

        # Test hauled status
        subject.is_active = False
        subject.save()
        serialized_gear = GearSerializer(subject_source1).data
        assert serialized_gear["status"] == "hauled"

        # Test single device case (should be type "single")
        subject_source2.delete()
        source2.delete()
        serialized_gear = GearSerializer(subject_source1).data
        assert serialized_gear["type"] == "single"
        assert len(serialized_gear["devices"]) == 1

    def test_with_multiple_subjects_same_name(self):
        """Test that each subject is serialized independently, even when subjects share the same name.

        Since the serializer now uses subject.id for filtering (not name), subjects with the same name
        are treated as separate gearsets. This test validates that behavior.
        """
        # Arrange
        # Create a subject subtype for ropeless_buoy_gearset
        subject_type = SubjectTypeFactory(value="gear")
        subject_subtype = SubjectSubType.objects.create(
            value=BUOY_GEAR_SUBJECT_SUBTYPE, display="Ropeless Buoy Gearset", subject_type=subject_type
        )

        # Create two subjects with the same name
        subject1 = Subject.objects.create(name="Same_Name_Gearset", subject_subtype=subject_subtype, is_active=True)
        subject2 = Subject.objects.create(name="Same_Name_Gearset", subject_subtype=subject_subtype, is_active=True)

        # Create provider
        provider = SourceProvider.objects.create(display_name="Test Provider", provider_key="test_provider")

        # Create sources for both subjects
        source1 = Source.objects.create(manufacturer_id="mfr_device_001", provider=provider)
        source2 = Source.objects.create(manufacturer_id="mfr_device_002", provider=provider)
        source3 = Source.objects.create(manufacturer_id="mfr_device_003", provider=provider)

        # Create observations for all sources
        now = timezone.now()
        location1 = Point(-24.43071, 31.19239)
        location2 = Point(-24.44071, 31.20239)
        location3 = Point(-24.45071, 31.21239)

        Observation.objects.create(recorded_at=now, location=location1, source=source1)
        Observation.objects.create(recorded_at=now, location=location2, source=source2)
        Observation.objects.create(recorded_at=now, location=location3, source=source3)

        deployment_time = now
        time_range = DateTimeTZRange(deployment_time, None)  # Open-ended range

        # Create SubjectSource relationships - subject1 has 1 source, subject2 has 2 sources
        subject_source1 = SubjectSource.objects.create(subject=subject1, source=source1, assigned_range=time_range)
        subject_source2 = SubjectSource.objects.create(subject=subject2, source=source2, assigned_range=time_range)
        # Add third source to subject2
        subject_source3 = SubjectSource.objects.create(subject=subject2, source=source3, assigned_range=time_range)

        # Act - serialize subject1 (should only include its own device)
        serialized_gear1 = GearSerializer(subject_source1).data

        # Assert for subject1 - only has 1 device
        assert serialized_gear1["id"] == str(subject1.id)
        assert serialized_gear1["display_id"] == "Same_Name_Gearset"
        assert serialized_gear1["status"] == "deployed"
        assert serialized_gear1["type"] == "single"  # Only 1 device for subject1
        assert "devices" in serialized_gear1
        assert len(serialized_gear1["devices"]) == 1  # Only subject1's device

        # Check device ID
        devices1 = serialized_gear1["devices"]
        device_ids1 = [device["device_id"] for device in devices1]
        assert str(source1.id) in device_ids1

        # Act - serialize subject2 (should include its 2 devices)
        serialized_gear2 = GearSerializer(subject_source2).data

        # Assert for subject2 - has 2 devices
        assert serialized_gear2["id"] == str(subject2.id)
        assert serialized_gear2["display_id"] == "Same_Name_Gearset"
        assert serialized_gear2["status"] == "deployed"
        assert serialized_gear2["type"] == "trawl"  # Has 2 devices for subject2
        assert "devices" in serialized_gear2
        assert len(serialized_gear2["devices"]) == 2  # Both of subject2's devices

        # Check device IDs for subject2
        devices2 = serialized_gear2["devices"]
        device_ids2 = [device["device_id"] for device in devices2]
        assert str(source2.id) in device_ids2
        assert str(source3.id) in device_ids2
        # subject1's device should NOT be in subject2's serialization
        assert str(source1.id) not in device_ids2


class TestGearCreateSerializer(BaseAPITest):
    def test_save_single_device(self):
        now = timezone.now()
        device_id = "123e4567-e89b-12d3-a456-426614174000"
        data = {
            "owner_id": "owner123",
            "mfr_set_id": "SET123",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id,
                    "mfr_device_id": "mfr123",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 1.23, "longitude": 4.56},
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 99})
        assert serializer.is_valid(), serializer.errors

        # Use BuoyService instead of serializer.save()
        subject, observations = BuoyService.process_gearset(serializer.validated_data, manufacturer="test_manufacturer")

        assert isinstance(observations, list)
        assert len(observations) == 1
        obs = observations[0]

        # Check observation fields - device_id is now Source.id
        assert str(obs.source.id) == device_id
        assert obs.source.manufacturer_id == "mfr123"
        assert obs.location.x == 4.56  # longitude
        assert obs.location.y == 1.23  # latitude
        assert obs.additional["raw"]["owner_id"] == "owner123"
        assert obs.additional["raw"]["deployment_type"] == "single"
        assert len(obs.additional["raw"]["devices"]) == 1
        assert obs.additional["raw"]["devices"][0]["device_id"] == device_id
        assert obs.additional["raw"]["devices"][0]["mfr_device_id"] == "mfr123"
        assert obs.additional["raw"]["devices"][0]["device_status"] == "deployed"

    def test_save_multiple_devices(self):
        now = timezone.now()
        device_id_1 = "223e4567-e89b-12d3-a456-426614174000"
        device_id_2 = "323e4567-e89b-12d3-a456-426614174000"
        data = {
            "owner_id": "ownerXYZ",
            "mfr_set_id": "SET_TRAWL_001",
            "deployment_type": "trawl",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id_1,
                    "mfr_device_id": "mfrA",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 0.0, "longitude": 0.0},
                },
                {
                    "device_id": device_id_2,
                    "mfr_device_id": "mfrB",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 9.99, "longitude": 9.99},
                },
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 7})
        assert serializer.is_valid(), serializer.errors

        # Use BuoyService instead of serializer.save()
        subject, observations = BuoyService.process_gearset(serializer.validated_data, manufacturer="test_manufacturer")

        assert isinstance(observations, list)
        # Two observations returned
        assert len(observations) == 2

        # Check that they share the same subject (gearset)
        subjects = {obs.source.subjectsource_set.first().subject for obs in observations}
        assert len(subjects) == 1

        # Check locations and source IDs are correct
        assert str(observations[0].source.id) == device_id_1
        assert observations[0].source.manufacturer_id == "mfrA"
        assert observations[0].location.x == 0.0  # longitude
        assert observations[0].location.y == 0.0  # latitude

        assert str(observations[1].source.id) == device_id_2
        assert observations[1].source.manufacturer_id == "mfrB"
        assert observations[1].location.x == 9.99  # longitude
        assert observations[1].location.y == 9.99  # latitude

    def test_save_device_without_mfr_device_id(self):
        """Test that mfr_device_id defaults to device_id when not provided."""
        now = timezone.now()
        device_id = "523e4567-e89b-12d3-a456-426614174000"
        data = {
            "owner_id": "owner456",
            "mfr_set_id": "SET456",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id,
                    # No mfr_device_id provided - should default to device_id
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 2.34, "longitude": 5.67},
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 100})
        assert serializer.is_valid(), serializer.errors

        # Verify that mfr_device_id was set to device_id
        validated_data = serializer.validated_data
        assert "mfr_device_id" in validated_data["devices"][0]
        mfr_device_id = validated_data["devices"][0]["mfr_device_id"]

        assert mfr_device_id == device_id

        # Use BuoyService to process and verify it works
        subject, observations = BuoyService.process_gearset(validated_data, manufacturer="test_manufacturer")

        assert isinstance(observations, list)
        assert len(observations) == 1
        obs = observations[0]

        # Check that the source was created with device_id as both Source.id and manufacturer_id
        assert str(obs.source.id) == device_id
        assert obs.source.manufacturer_id == device_id
        assert obs.location.x == 5.67  # longitude
        assert obs.location.y == 2.34  # latitude

    def test_set_level_defaults(self):
        """Test that mfr_set_id defaults to set_id and set_display_id defaults to mfr_set_id."""
        now = timezone.now()
        device_id = "623e4567-e89b-12d3-a456-426614174000"

        # Case 1: mfr_set_id provided but not set_display_id - both should be set correctly
        data = {
            "owner_id": "owner999",
            "mfr_set_id": "CUSTOM_MFR_999",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id,
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 3.45, "longitude": 6.78},
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 102})
        assert serializer.is_valid(), serializer.errors

        validated_data = serializer.validated_data
        set_id = validated_data["set_id"]

        # set_id should be generated
        assert set_id is not None

        # mfr_set_id should be the provided value
        assert validated_data["mfr_set_id"] == "CUSTOM_MFR_999"

        # set_display_id should default to mfr_set_id
        assert validated_data["set_display_id"] == "CUSTOM_MFR_999"

        # Case 2: Both mfr_set_id and set_display_id provided
        custom_set_display_id = "DISPLAY_456"
        data_with_both = {
            "owner_id": "owner997",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "mfr_set_id": "CUSTOM_MFR_997",
            "set_display_id": custom_set_display_id,
            "devices": [
                {
                    "device_id": device_id,
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 5.67, "longitude": 8.90},
                }
            ],
        }
        serializer2 = GearCreateSerializer(data=data_with_both, context={"user_id": 104})
        assert serializer2.is_valid(), serializer2.errors

        validated_data2 = serializer2.validated_data

        # Both should retain their provided values
        assert validated_data2["mfr_set_id"] == "CUSTOM_MFR_997"
        assert validated_data2["set_display_id"] == custom_set_display_id

    def test_device_id_required(self):
        """Test that device_id is required."""
        now = timezone.now()
        data = {
            "owner_id": "owner789",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    # No device_id provided - should fail validation
                    "mfr_device_id": "mfr789",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 3.45, "longitude": 6.78},
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 101})
        assert not serializer.is_valid()
        assert "device_id" in json.dumps(serializer.errors)
        assert "required" in json.dumps(serializer.errors).lower()

    def test_set_id_required_without_mfr_set_id(self):
        """Test that set_id cannot be determined without mfr_set_id or set_id."""
        now = timezone.now()
        device_id = "723e4567-e89b-12d3-a456-426614174000"
        data = {
            "owner_id": "owner888",
            "deployment_type": "single",
            "initial_deployment_date": now,
            # No set_id and no mfr_set_id provided
            "devices": [
                {
                    "device_id": device_id,
                    "mfr_device_id": "mfr888",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 6.78, "longitude": 9.01},
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 105})
        assert not serializer.is_valid()
        assert "set_id" in serializer.errors
        assert "Cannot determine set_id" in str(serializer.errors["set_id"])

    def test_mfr_set_id_lookup_finds_existing_subject(self):
        """Test that providing mfr_set_id finds existing Subject by name."""
        now = timezone.now()

        # First, create a subject with a specific mfr_set_id
        device_id_1 = "823e4567-e89b-12d3-a456-426614174000"
        mfr_set_id = "LOOKUP_TEST_SET"
        data = {
            "owner_id": "owner777",
            "mfr_set_id": mfr_set_id,
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id_1,
                    "mfr_device_id": "mfr_lookup_1",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 7.89, "longitude": 10.11},
                }
            ],
        }
        serializer1 = GearCreateSerializer(data=data, context={"user_id": 106})
        assert serializer1.is_valid(), serializer1.errors

        # Create the subject
        subject1, observations1 = BuoyService.process_gearset(
            serializer1.validated_data, manufacturer="test_manufacturer"
        )
        first_set_id = subject1.id

        # Now POST again with the same mfr_set_id (but different device)
        device_id_2 = "923e4567-e89b-12d3-a456-426614174000"
        data2 = {
            "owner_id": "owner777",
            "mfr_set_id": mfr_set_id,  # Same mfr_set_id
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id_2,
                    "mfr_device_id": "mfr_lookup_2",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 8.90, "longitude": 11.12},
                }
            ],
        }
        serializer2 = GearCreateSerializer(data=data2, context={"user_id": 107})
        assert serializer2.is_valid(), serializer2.errors

        # The set_id should be the same as the first one (found by mfr_set_id)
        assert serializer2.validated_data["set_id"] == first_set_id


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
        "device_id": "123e4567-e89b-12d3-a456-426614174000",
        "mfr_device_id": "dev1",
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
        "device_id": "223e4567-e89b-12d3-a456-426614174000",
        "mfr_device_id": "dev1",
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
        "mfr_set_id": "SET_MISMATCH",
        "deployment_type": "single",
        "initial_deployment_date": now.isoformat(),
        "devices_in_set": 2,
        "devices": [
            {
                "device_id": "123e4567-e89b-12d3-a456-426614174000",
                "mfr_device_id": "mfr1",
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
        "mfr_set_id": "SET_HAUL_TEST",
        "deployment_type": "single",
        "initial_deployment_date": now.isoformat(),
        "devices": [
            {
                "device_id": "223e4567-e89b-12d3-a456-426614174000",
                "mfr_device_id": "mfr-not-exist",
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
    # Create subject and sources that match device ids (Source.id)
    subject = Subject.objects.create(name="SET123", subject_subtype=None, is_active=True)
    provider = SourceProvider.objects.create(display_name="P", provider_key="pkey")

    # Create sources with specific IDs
    from uuid import UUID

    source_id_1 = UUID("aaaaaaaa-e89b-12d3-a456-426614174000")
    source_id_2 = UUID("bbbbbbbb-e89b-12d3-a456-426614174000")

    src1 = Source.objects.create(id=source_id_1, manufacturer_id="mfr_A", provider=provider)
    src2 = Source.objects.create(id=source_id_2, manufacturer_id="mfr_B", provider=provider)

    now = timezone.now()
    rng = DateTimeTZRange(now - timedelta(days=1), None)
    SubjectSource.objects.create(subject=subject, source=src1, assigned_range=rng)
    SubjectSource.objects.create(subject=subject, source=src2, assigned_range=rng)

    serializer = GearCreateSerializer()
    # device_id is now Source.id
    set_id = serializer._get_gearset_id({}, [{"device_id": str(source_id_1)}, {"device_id": str(source_id_2)}])
    assert set_id == subject.id


@pytest.mark.django_db
def test_gear_serializer_devices_and_manufacturer():
    # Ensure GearSerializer returns devices and prefers additional manufacturer
    subject = Subject.objects.create(name="S1", subject_subtype=None, is_active=True)
    subject.additional = {"manufacturer": "acme"}
    subject.save()
    provider = SourceProvider.objects.create(display_name="P", provider_key="gundi_acme_1234")
    src = Source.objects.create(manufacturer_id="mfr_dev1", provider=provider)
    now = timezone.now()

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
    assert dev["device_id"] == str(src.id)  # device_id is Source.id
    assert dev["mfr_device_id"] == "mfr_dev1"  # mfr_device_id is Source.manufacturer_id
    assert dev["location"]["latitude"] == pytest.approx(31.19)
