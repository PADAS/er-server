import pytest
from dateutil import parser as date_parser
from psycopg2.extras import DateTimeTZRange

from django.contrib.gis.geos import Point
from django.utils import timezone

from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from buoy.serializers import GearCreateSerializer, GearSerializer
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
        source2 = Source.objects.create(manufacturer_id="device_002", provider=provider)

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
        assert gear_subjectsource.source.manufacturer_id in device_ids
        assert "device_002" in device_ids

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
        assert device["device_id"] == source.manufacturer_id

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
            manufacturer_id="device_001", provider=provider, additional={"last_deployed": "2024-10-16T11:08:17-08:00"}
        )

        source2 = Source.objects.create(
            manufacturer_id="device_002", provider=provider, additional={"last_deployed": "2024-10-16T12:15:22-08:00"}
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
        assert "device_001" in device_ids
        assert "device_002" in device_ids

        # Check first device
        device1 = next(d for d in devices if d["device_id"] == "device_001")
        assert device1["label"] == "a"  # First device should get label 'a'
        assert "location" in device1
        assert device1["location"]["latitude"] == 31.19239
        assert device1["location"]["longitude"] == -24.43071
        assert "last_deployed" in device1  # Check it exists (datetime object from assigned_range.lower)

        # Check second device
        device2 = next(d for d in devices if d["device_id"] == "device_002")
        assert device2["label"] == "b"  # Second device should get label 'b'
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
        """Test that devices from all subjects with the same name are included."""
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
        source1 = Source.objects.create(manufacturer_id="device_001", provider=provider)
        source2 = Source.objects.create(manufacturer_id="device_002", provider=provider)
        source3 = Source.objects.create(manufacturer_id="device_003", provider=provider)

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
        SubjectSource.objects.create(subject=subject2, source=source3, assigned_range=time_range)

        # Act - serialize using subject1, but should get devices from both subjects with same name
        serialized_gear = GearSerializer(subject_source1).data

        # Assert
        assert serialized_gear["id"] == str(subject1.id)
        assert serialized_gear["display_id"] == "Same_Name_Gearset"
        assert serialized_gear["status"] == "deployed"
        assert serialized_gear["type"] == "trawl"  # Should be trawl since > 1 device (3 total)
        assert "devices" in serialized_gear
        assert len(serialized_gear["devices"]) == 3  # Should include devices from both subjects

        # Check all device IDs are present
        devices = serialized_gear["devices"]
        device_ids = [device["device_id"] for device in devices]
        assert "device_001" in device_ids
        assert "device_002" in device_ids
        assert "device_003" in device_ids

        # Test with subject2 as well - should return the same devices
        serialized_gear2 = GearSerializer(subject_source2).data
        assert len(serialized_gear2["devices"]) == 3
        device_ids2 = [device["device_id"] for device in serialized_gear2["devices"]]
        assert set(device_ids) == set(device_ids2)  # Same devices regardless of which subject we serialize


class TestGearCreateSerializer(BaseAPITest):
    def test_save_single_device(self):
        now = timezone.now()
        data = {
            "owner_id": "owner123",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": "123e4567-e89b-12d3-a456-426614174000",
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

        # Check observation fields
        assert obs.source.manufacturer_id == "123e4567-e89b-12d3-a456-426614174000"
        assert obs.location.x == 4.56  # longitude
        assert obs.location.y == 1.23  # latitude
        assert obs.additional["raw"]["owner_id"] == "owner123"
        assert obs.additional["raw"]["deployment_type"] == "single"
        assert len(obs.additional["raw"]["devices"]) == 1
        assert obs.additional["raw"]["devices"][0]["device_id"] == "123e4567-e89b-12d3-a456-426614174000"
        assert obs.additional["raw"]["devices"][0]["device_status"] == "deployed"

    def test_save_multiple_devices(self):
        now = timezone.now()
        data = {
            "owner_id": "ownerXYZ",
            "deployment_type": "trawl",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": "223e4567-e89b-12d3-a456-426614174000",
                    "mfr_device_id": "mfrA",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 0.0, "longitude": 0.0},
                },
                {
                    "device_id": "323e4567-e89b-12d3-a456-426614174000",
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

        # Check locations are correct
        assert observations[0].location.x == 0.0  # longitude
        assert observations[0].location.y == 0.0  # latitude
        assert observations[1].location.x == 9.99  # longitude
        assert observations[1].location.y == 9.99  # latitude

    def test_save_device_without_device_id(self):
        """Test that device_id is auto-generated when not provided."""
        now = timezone.now()
        data = {
            "owner_id": "owner456",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    # No device_id provided - should be auto-generated
                    "mfr_device_id": "mfr456",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 2.34, "longitude": 5.67},
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 100})
        assert serializer.is_valid(), serializer.errors

        # Verify that device_id was auto-generated
        validated_data = serializer.validated_data
        assert "device_id" in validated_data["devices"][0]
        device_id = validated_data["devices"][0]["device_id"]
        from uuid import UUID

        assert isinstance(device_id, UUID)

        # Use BuoyService to process and verify it works
        subject, observations = BuoyService.process_gearset(validated_data, manufacturer="test_manufacturer")

        assert isinstance(observations, list)
        assert len(observations) == 1
        obs = observations[0]

        # Check that the source was created with the auto-generated device_id
        assert obs.source.manufacturer_id == str(device_id)
        assert obs.location.x == 5.67  # longitude
        assert obs.location.y == 2.34  # latitude
