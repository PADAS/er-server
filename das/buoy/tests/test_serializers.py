import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
from dateutil import parser as date_parser
from psycopg2.extras import DateTimeTZRange

from django.contrib.gis.geos import Point
from django.utils import timezone

from accounts.models import PermissionSet
from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from buoy.serializers import GearCreateSerializer, GearSerializer
from buoy.serializers.gear import GearDeviceCreateSerializer, GeoLocationSerializer
from buoy.services.buoy_service import BuoyService
from core.tests import BaseAPITest
from factories import SubjectTypeFactory
from observations.models import (
    EMPTY_POINT,
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectGroup,
    SubjectSource,
    SubjectSubType,
)


def _create_mock_request(user):
    """Helper to create a mock request with a user for serializer context."""
    request = Mock()
    request.user = user
    return request


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
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="testuser", password="testpass")

        # Create SubjectGroup and assign permission to user
        subject_group = SubjectGroup.objects.create(name="TestManufacturer")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        user.permission_sets.add(permission_set)

        now = timezone.now()
        device_id = "123e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestManufacturer",
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
                    "recorded_at": now,
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(user)})
        assert serializer.is_valid(), serializer.errors

        # Use BuoyService instead of serializer.save()
        subject, observations = BuoyService.process_gearset(serializer.validated_data, user=user)

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
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="testuser2", password="testpass")

        # Create SubjectGroup and assign permission to user
        subject_group = SubjectGroup.objects.create(name="TestManufacturer2")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        user.permission_sets.add(permission_set)

        now = timezone.now()
        device_id_1 = "223e4567-e89b-12d3-a456-426614174000"
        device_id_2 = "323e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestManufacturer2",
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
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(user)})
        assert serializer.is_valid(), serializer.errors

        # Use BuoyService instead of serializer.save()
        subject, observations = BuoyService.process_gearset(serializer.validated_data, user=user)

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
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="testuser3", password="testpass")

        # Create SubjectGroup and assign permission to user
        subject_group = SubjectGroup.objects.create(name="TestManufacturer3")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        user.permission_sets.add(permission_set)

        now = timezone.now()
        device_id = "523e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestManufacturer3",
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
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(user)})
        assert serializer.is_valid(), serializer.errors

        # Verify that mfr_device_id was set to device_id
        validated_data = serializer.validated_data
        assert "mfr_device_id" in validated_data["devices"][0]
        mfr_device_id = validated_data["devices"][0]["mfr_device_id"]

        assert mfr_device_id == device_id

        # Use BuoyService to process and verify it works
        subject, observations = BuoyService.process_gearset(validated_data, user=user)

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
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="testuser4", password="testpass")

        # Create SubjectGroup and assign permission to user
        subject_group = SubjectGroup.objects.create(name="TestManufacturer4")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        user.permission_sets.add(permission_set)

        now = timezone.now()
        device_id = "623e4567-e89b-12d3-a456-426614174000"

        # Case 1: mfr_set_id provided but not set_display_id - both should be set correctly
        data = {
            "manufacturer_name": "TestManufacturer4",
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
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(user)})
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
            "manufacturer_name": "TestManufacturer4",
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
        serializer2 = GearCreateSerializer(data=data_with_both, context={"request": _create_mock_request(user)})
        assert serializer2.is_valid(), serializer2.errors

        validated_data2 = serializer2.validated_data

        # Both should retain their provided values
        assert validated_data2["mfr_set_id"] == "CUSTOM_MFR_997"
        assert validated_data2["set_display_id"] == custom_set_display_id

    def test_device_id_required(self):
        """Test that device_id is required."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="testuser5", password="testpass")

        # Create SubjectGroup and assign permission to user
        subject_group = SubjectGroup.objects.create(name="TestManufacturer5")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        user.permission_sets.add(permission_set)

        now = timezone.now()
        data = {
            "manufacturer_name": "TestManufacturer5",
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
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(user)})
        assert not serializer.is_valid()
        assert "device_id" in json.dumps(serializer.errors)
        assert "required" in json.dumps(serializer.errors).lower()

    def test_set_id_required_without_mfr_set_id(self):
        """Test that set_id cannot be determined without mfr_set_id or set_id."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="testuser6", password="testpass")

        # Create SubjectGroup and assign permission to user
        subject_group = SubjectGroup.objects.create(name="TestManufacturer6")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        user.permission_sets.add(permission_set)

        now = timezone.now()
        device_id = "723e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestManufacturer6",
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
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(user)})
        assert not serializer.is_valid()
        assert "set_id" in serializer.errors
        assert "Cannot determine set_id" in str(serializer.errors["set_id"])

    def test_mfr_set_id_lookup_finds_existing_subject(self):
        """Test that providing mfr_set_id finds existing Subject by name."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="testuser_lookup", password="testpass")

        # Create SubjectGroup and assign permission to user
        subject_group = SubjectGroup.objects.create(name="TestManufacturerLookup")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        user.permission_sets.add(permission_set)

        now = timezone.now()

        # First, create a subject with a specific mfr_set_id
        device_id_1 = "823e4567-e89b-12d3-a456-426614174000"
        mfr_set_id = "LOOKUP_TEST_SET"
        data = {
            "manufacturer_name": "TestManufacturerLookup",
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
        serializer1 = GearCreateSerializer(data=data, context={"request": _create_mock_request(user)})
        assert serializer1.is_valid(), serializer1.errors

        # Create the subject
        subject1, observations1 = BuoyService.process_gearset(serializer1.validated_data, user=user)
        first_set_id = subject1.id

        # Now POST again with the same mfr_set_id (but different device)
        device_id_2 = "923e4567-e89b-12d3-a456-426614174000"
        data2 = {
            "manufacturer_name": "TestManufacturerLookup",
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
        serializer2 = GearCreateSerializer(data=data2, context={"request": _create_mock_request(user)})
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
def test_gear_create_devices_in_set_and_haul_validation():
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(username="testuser_validation", password="testpass")

    # Create SubjectGroup and assign permission to user
    subject_group = SubjectGroup.objects.create(name="TestManufacturerValidation")
    permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
    subject_group.permission_sets.add(permission_set)
    user.permission_sets.add(permission_set)

    now = timezone.now()
    # devices_in_set mismatch
    payload = {
        "manufacturer_name": "TestManufacturerValidation",
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
    s = GearCreateSerializer(data=payload, context={"request": _create_mock_request(user)})
    assert not s.is_valid()
    assert "devices_in_set" in json.dumps(s.errors)

    # Hauling a device that's not deployed should error
    payload = {
        "manufacturer_name": "TestManufacturerValidation",
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
    s = GearCreateSerializer(data=payload, context={"request": _create_mock_request(user)})
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


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_process_gearset_adds_subject_to_subjectgroup(superuser):
    """Test that process_gearset adds the subject to the correct SubjectGroup."""
    # Create SubjectGroup and assign permission to superuser
    subject_group = SubjectGroup.objects.create(name="TestProcessManufacturer")
    permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
    subject_group.permission_sets.add(permission_set)
    superuser.permission_sets.add(permission_set)

    now = timezone.now()
    device_id = "123e4567-e89b-12d3-a456-426614174000"

    data = {
        "manufacturer_name": "TestProcessManufacturer",
        "owner_id": "owner123",
        "mfr_set_id": "TEST_SET_123",
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

    serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors

    # Process gearset with user parameter
    subject, observations = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    # Verify that the subject was added to the SubjectGroup
    assert subject_group in subject.groups.all()

    # Verify the subject has the correct manufacturer in additional
    assert subject.additional.get("manufacturer") == "TestProcessManufacturer"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_process_gearset_reuses_source_by_id_when_manufacturer_id_differs(superuser):
    """Reusing Source by device_id (id) avoids duplicate key when mfr_device_id differs from existing."""
    from uuid import UUID

    subject_group = SubjectGroup.objects.create(name="ReuseSourceManufacturer")
    permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
    subject_group.permission_sets.add(permission_set)
    superuser.permission_sets.add(permission_set)

    # Existing Source with this id but different manufacturer_id (e.g. from an earlier POST)
    device_uuid = UUID("440fd840-728b-4742-a3e5-7c8f67b5212b")
    provider = SourceProvider.objects.create(
        display_name="ReuseSourceManufacturer", provider_key="gundi_reusesourcemanufacturer"
    )
    existing_source = Source.objects.create(
        id=device_uuid,
        manufacturer_id="original_mfr_id",
        provider=provider,
    )
    assert existing_source.manufacturer_id == "original_mfr_id"

    now = timezone.now()
    data = {
        "manufacturer_name": "ReuseSourceManufacturer",
        "owner_id": "owner123",
        "mfr_set_id": "SET_REUSE_1",
        "deployment_type": "single",
        "initial_deployment_date": now,
        "devices": [
            {
                "device_id": str(device_uuid),
                "mfr_device_id": "different_mfr_id",
                "last_deployed": now,
                "last_updated": now,
                "device_status": "deployed",
                "location": {"latitude": 1.0, "longitude": 2.0},
            }
        ],
    }

    serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors

    # Should not raise IntegrityError; existing Source is reused by id
    subject, observations = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    assert len(observations) == 1
    assert observations[0].source_id == device_uuid
    # Reused source keeps its original manufacturer_id (we do not overwrite it)
    existing_source.refresh_from_db()
    assert existing_source.manufacturer_id == "original_mfr_id"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_process_gearset_updates_existing_subject_keeps_subjectgroup(superuser):
    """Test that process_gearset maintains SubjectGroup membership when updating existing subject."""
    # Create SubjectGroup and assign permission to superuser
    subject_group = SubjectGroup.objects.create(name="TestUpdateManufacturer")
    permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
    subject_group.permission_sets.add(permission_set)
    superuser.permission_sets.add(permission_set)

    now = timezone.now()
    device_id = "223e4567-e89b-12d3-a456-426614174000"

    # Create a subject
    subject_subtype = SubjectSubType.objects.get_or_create(value=BUOY_GEAR_SUBJECT_SUBTYPE)[0]
    existing_subject = Subject.objects.create(
        name="existing_gear", subject_subtype=subject_subtype, additional={"display_id": "existing_gear"}
    )

    data = {
        "manufacturer_name": "TestUpdateManufacturer",
        "set_id": str(existing_subject.id),
        "owner_id": "owner123",
        "deployment_type": "single",
        "initial_deployment_date": now,
        "devices": [
            {
                "device_id": device_id,
                "mfr_device_id": "mfr456",
                "last_deployed": now,
                "last_updated": now,
                "device_status": "deployed",
                "location": {"latitude": 2.34, "longitude": 5.67},
            }
        ],
    }

    serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors

    # Process gearset with user parameter
    subject, observations = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    # Verify the existing subject is returned
    assert subject.id == existing_subject.id

    # Verify that the subject was added to the SubjectGroup
    assert subject_group in subject.groups.all()

    # Verify the subject has the correct manufacturer in additional
    assert subject.additional.get("manufacturer") == "TestUpdateManufacturer"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_process_gearset_sets_is_active_false_when_all_hauled(superuser):
    """Test that process_gearset sets subject.is_active=False when all devices are hauled.

    This test verifies that when haul time is in the past (relative to deployment),
    the is_active flag is correctly set to False.
    """
    from observations.models import DEFAULT_ASSIGNED_RANGE

    # Create SubjectGroup and assign permission to superuser
    subject_group = SubjectGroup.objects.create(name="TestHaulManufacturer")
    permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
    subject_group.permission_sets.add(permission_set)
    superuser.permission_sets.add(permission_set)

    now = timezone.now()
    deploy_time = now - timedelta(hours=1)  # Deployed 1 hour ago
    haul_time = now - timedelta(minutes=5)  # Hauled 5 minutes ago
    device_id = "333e4567-e89b-12d3-a456-426614174000"

    # First, deploy the gearset (with recorded_at in the past)
    deploy_data = {
        "manufacturer_name": "TestHaulManufacturer",
        "owner_id": "owner123",
        "mfr_set_id": "TEST_HAUL_SET",
        "deployment_type": "single",
        "initial_deployment_date": deploy_time,
        "devices": [
            {
                "device_id": device_id,
                "mfr_device_id": "mfr_haul_test",
                "last_deployed": deploy_time,
                "last_updated": deploy_time,
                "device_status": "deployed",
                "location": {"latitude": 1.23, "longitude": 4.56},
                "recorded_at": deploy_time,
            }
        ],
    }

    serializer = GearCreateSerializer(data=deploy_data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors
    subject, _ = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    # Verify subject is active after deployment
    subject.refresh_from_db()
    assert subject.is_active is True

    # Verify SubjectSource has upper bound at datetime.max (deployed)
    subject_source = SubjectSource.objects.get(subject=subject)
    assert subject_source.assigned_range.upper == DEFAULT_ASSIGNED_RANGE[1]

    # Now haul the gearset - haul_time is after deploy_time but before now
    haul_data = {
        "manufacturer_name": "TestHaulManufacturer",
        "owner_id": "owner123",
        "set_id": str(subject.id),
        "mfr_set_id": "TEST_HAUL_SET",
        "deployment_type": "single",
        "devices": [
            {
                "device_id": device_id,
                "mfr_device_id": "mfr_haul_test",
                "last_deployed": deploy_time,
                "last_updated": now,
                "device_status": "hauled",
                "location": {"latitude": 1.23, "longitude": 4.56},
                "recorded_at": haul_time,
            }
        ],
    }

    serializer = GearCreateSerializer(data=haul_data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors
    subject, _ = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    # Verify SubjectSource has upper bound set (not datetime.max)
    subject_source.refresh_from_db()
    assert subject_source.assigned_range.upper != DEFAULT_ASSIGNED_RANGE[1]
    assert subject_source.assigned_range.upper < now  # Upper bound should be in the past

    # This is the critical assertion - is_active should be False after all devices are hauled
    subject.refresh_from_db()
    assert subject.is_active is False, (
        f"Subject is_active should be False after haul. "
        f"assigned_range.upper={subject_source.assigned_range.upper}, now={now}"
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_process_gearset_is_active_false_with_recent_recorded_at(superuser):
    """Test that process_gearset sets is_active=False even when recorded_at is very recent.

    This test specifically tests the race condition where recorded_at is the current time,
    causing the 1-second padding to make 'now in assigned_range' return True.
    """
    from observations.models import DEFAULT_ASSIGNED_RANGE

    # Create SubjectGroup and assign permission to superuser
    subject_group = SubjectGroup.objects.create(name="TestRecentHaulManufacturer")
    permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
    subject_group.permission_sets.add(permission_set)
    superuser.permission_sets.add(permission_set)

    now = timezone.now()
    device_id = "444e4567-e89b-12d3-a456-426614174000"

    # First, deploy the gearset
    deploy_data = {
        "manufacturer_name": "TestRecentHaulManufacturer",
        "owner_id": "owner123",
        "mfr_set_id": "TEST_RECENT_HAUL_SET",
        "deployment_type": "single",
        "initial_deployment_date": now,
        "devices": [
            {
                "device_id": device_id,
                "mfr_device_id": "mfr_recent_haul_test",
                "last_deployed": now,
                "last_updated": now,
                "device_status": "deployed",
                "location": {"latitude": 1.23, "longitude": 4.56},
                "recorded_at": now,
            }
        ],
    }

    serializer = GearCreateSerializer(data=deploy_data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors
    subject, _ = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    # Now haul the gearset - use current time (this is the race condition scenario)
    # The bug is that 'now not in assigned_range' will be False because now < upper (recorded_at + 1s)
    haul_time = timezone.now()  # Very recent - this triggers the bug
    haul_data = {
        "manufacturer_name": "TestRecentHaulManufacturer",
        "owner_id": "owner123",
        "set_id": str(subject.id),
        "mfr_set_id": "TEST_RECENT_HAUL_SET",
        "deployment_type": "single",
        "devices": [
            {
                "device_id": device_id,
                "mfr_device_id": "mfr_recent_haul_test",
                "last_deployed": now,
                "last_updated": haul_time,
                "device_status": "hauled",
                "location": {"latitude": 1.23, "longitude": 4.56},
                "recorded_at": haul_time,
            }
        ],
    }

    serializer = GearCreateSerializer(data=haul_data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors
    subject, _ = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    # Verify SubjectSource has upper bound set (not datetime.max)
    subject_source = SubjectSource.objects.get(subject=subject)
    assert subject_source.assigned_range.upper != DEFAULT_ASSIGNED_RANGE[1]

    # This assertion will FAIL with the current buggy code because 'now' might still
    # be within the 1-second window of the upper bound
    subject.refresh_from_db()
    assert subject.is_active is False, (
        f"Subject is_active should be False after haul even with recent recorded_at. "
        f"assigned_range.upper={subject_source.assigned_range.upper}"
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_auto_haul_all_devices_when_one_device_hauled(superuser):
    """Test that hauling one device in a multi-device gearset auto-hauls all other devices.

    This test verifies the auto-haul behavior: when a gearset has multiple devices
    and only one device is included in the haul notification, all other deployed
    devices are automatically hauled using the same haul timestamp.
    """
    from observations.models import DEFAULT_ASSIGNED_RANGE

    # Create SubjectGroup and assign permission to superuser
    subject_group = SubjectGroup.objects.create(name="TestAutoHaulManufacturer")
    permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
    subject_group.permission_sets.add(permission_set)
    superuser.permission_sets.add(permission_set)

    now = timezone.now()
    deploy_time = now - timedelta(hours=2)
    haul_time = now - timedelta(minutes=10)

    device_id_1 = "111e4567-e89b-12d3-a456-426614174001"
    device_id_2 = "222e4567-e89b-12d3-a456-426614174002"

    # Deploy gearset with TWO devices
    deploy_data = {
        "manufacturer_name": "TestAutoHaulManufacturer",
        "owner_id": "owner_auto_haul",
        "mfr_set_id": "TEST_AUTO_HAUL_SET",
        "deployment_type": "trawl",
        "initial_deployment_date": deploy_time,
        "devices": [
            {
                "device_id": device_id_1,
                "mfr_device_id": "mfr_auto_haul_1",
                "last_deployed": deploy_time,
                "last_updated": deploy_time,
                "device_status": "deployed",
                "location": {"latitude": 42.0, "longitude": -70.0},
                "recorded_at": deploy_time,
            },
            {
                "device_id": device_id_2,
                "mfr_device_id": "mfr_auto_haul_2",
                "last_deployed": deploy_time,
                "last_updated": deploy_time,
                "device_status": "deployed",
                "location": {"latitude": 42.1, "longitude": -70.1},
                "recorded_at": deploy_time,
            },
        ],
    }

    serializer = GearCreateSerializer(data=deploy_data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors
    subject, _ = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    # Verify subject is active and both SubjectSources have open ranges
    subject.refresh_from_db()
    assert subject.is_active is True

    ss_1 = SubjectSource.objects.get(source_id=device_id_1)
    ss_2 = SubjectSource.objects.get(source_id=device_id_2)
    assert ss_1.assigned_range.upper == DEFAULT_ASSIGNED_RANGE[1]
    assert ss_2.assigned_range.upper == DEFAULT_ASSIGNED_RANGE[1]

    # Now haul the gearset with ONLY ONE device in the haul notification
    haul_data = {
        "manufacturer_name": "TestAutoHaulManufacturer",
        "owner_id": "owner_auto_haul",
        "set_id": str(subject.id),
        "mfr_set_id": "TEST_AUTO_HAUL_SET",
        "deployment_type": "trawl",
        "devices": [
            {
                "device_id": device_id_1,
                "mfr_device_id": "mfr_auto_haul_1",
                "last_deployed": deploy_time,
                "last_updated": now,
                "device_status": "hauled",
                "location": {"latitude": 42.0, "longitude": -70.0},
                "recorded_at": haul_time,
            },
            # device_id_2 is intentionally NOT included in the haul notification
        ],
    }

    serializer = GearCreateSerializer(data=haul_data, context={"request": _create_mock_request(superuser)})
    assert serializer.is_valid(), serializer.errors
    subject, _ = BuoyService.process_gearset(serializer.validated_data, user=superuser)

    # Verify BOTH SubjectSources are now hauled (ranges closed)
    ss_1.refresh_from_db()
    ss_2.refresh_from_db()

    assert (
        ss_1.assigned_range.upper != DEFAULT_ASSIGNED_RANGE[1]
    ), f"Device 1 should be hauled but assigned_range.upper={ss_1.assigned_range.upper}"
    assert (
        ss_2.assigned_range.upper != DEFAULT_ASSIGNED_RANGE[1]
    ), f"Device 2 should be auto-hauled but assigned_range.upper={ss_2.assigned_range.upper}"

    # Both devices should have haul time close to the same value (within 1 second padding)
    assert abs((ss_1.assigned_range.upper - ss_2.assigned_range.upper).total_seconds()) < 2

    # Subject should now be inactive (all devices hauled)
    subject.refresh_from_db()
    assert subject.is_active is False, (
        f"Subject should be inactive after auto-haul. "
        f"ss_1.upper={ss_1.assigned_range.upper}, ss_2.upper={ss_2.assigned_range.upper}"
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeviceWithNullLocation:
    """Tests for devices with null/missing location data (Edgetech use case)."""

    def test_serializer_accepts_null_location(self, superuser):
        """Test that GearDeviceCreateSerializer accepts null location."""

        now = timezone.now()
        data = {
            "device_id": "123e4567-e89b-12d3-a456-426614174000",
            "mfr_device_id": "mfr_null_loc",
            "last_deployed": now,
            "last_updated": now,
            "device_status": "deployed",
            "location": None,
        }
        serializer = GearDeviceCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data.get("location") is None

    def test_serializer_accepts_null_lat_lon_in_location_object(self, superuser):
        """Test that GearDeviceCreateSerializer accepts location object with null lat/lon (Edgetech format)."""

        now = timezone.now()
        data = {
            "device_id": "123e4567-e89b-12d3-a456-426614174000",
            "mfr_device_id": "mfr_null_lat_lon",
            "last_deployed": now,
            "last_updated": now,
            "device_status": "deployed",
            "location": {"latitude": None, "longitude": None},
        }
        serializer = GearDeviceCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        # Location object should be present with null values
        assert serializer.validated_data.get("location") is not None
        assert serializer.validated_data["location"]["latitude"] is None
        assert serializer.validated_data["location"]["longitude"] is None

    def test_serializer_accepts_missing_location(self, superuser):
        """Test that GearDeviceCreateSerializer accepts missing location field."""

        now = timezone.now()
        data = {
            "device_id": "123e4567-e89b-12d3-a456-426614174000",
            "mfr_device_id": "mfr_missing_loc",
            "last_deployed": now,
            "last_updated": now,
            "device_status": "deployed",
            # No location field at all
        }
        serializer = GearDeviceCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert "location" not in serializer.validated_data or serializer.validated_data.get("location") is None

    def test_gear_create_serializer_accepts_device_with_null_location(self, superuser):
        """Test that GearCreateSerializer accepts a device with null location."""
        # Create SubjectGroup and assign permission to superuser
        subject_group = SubjectGroup.objects.create(name="TestNullLocManufacturer")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser.permission_sets.add(permission_set)

        now = timezone.now()
        device_id = "123e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestNullLocManufacturer",
            "owner_id": "owner_null_loc",
            "mfr_set_id": "SET_NULL_LOC",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id,
                    "mfr_device_id": "mfr_null_loc_device",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": None,
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
        assert serializer.is_valid(), serializer.errors

    def test_process_gearset_with_null_location_creates_observation_with_empty_point(self, superuser):
        """Test that BuoyService creates Observation with EMPTY_POINT for device with null location."""

        # Create SubjectGroup and assign permission to superuser
        subject_group = SubjectGroup.objects.create(name="TestNullLocObsManufacturer")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser.permission_sets.add(permission_set)

        now = timezone.now()
        device_id = "223e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestNullLocObsManufacturer",
            "owner_id": "owner_null_loc_obs",
            "mfr_set_id": "SET_NULL_LOC_OBS",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id,
                    "mfr_device_id": "mfr_null_loc_obs_device",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": None,
                    "recorded_at": now,
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
        assert serializer.is_valid(), serializer.errors

        subject, observations = BuoyService.process_gearset(serializer.validated_data, user=superuser)

        # Verify observation was created with EMPTY_POINT
        assert len(observations) == 1
        obs = observations[0]
        assert obs.location == EMPTY_POINT, f"Expected EMPTY_POINT, got {obs.location}"

    def test_process_gearset_with_null_location_sets_subjectsource_location_to_none(self, superuser):
        """Test that BuoyService sets SubjectSource.location to None for device with null location."""
        # Create SubjectGroup and assign permission to superuser
        subject_group = SubjectGroup.objects.create(name="TestNullLocSSManufacturer")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser.permission_sets.add(permission_set)

        now = timezone.now()
        device_id = "323e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestNullLocSSManufacturer",
            "owner_id": "owner_null_loc_ss",
            "mfr_set_id": "SET_NULL_LOC_SS",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id,
                    "mfr_device_id": "mfr_null_loc_ss_device",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": None,
                    "recorded_at": now,
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
        assert serializer.is_valid(), serializer.errors

        subject, observations = BuoyService.process_gearset(serializer.validated_data, user=superuser)

        # Verify SubjectSource was created with null location
        subject_source = SubjectSource.objects.get(subject=subject)
        assert subject_source.location is None, f"Expected None, got {subject_source.location}"

    def test_process_gearset_with_missing_location_field(self, superuser):
        """Test that BuoyService handles device with entirely missing location field."""

        # Create SubjectGroup and assign permission to superuser
        subject_group = SubjectGroup.objects.create(name="TestMissingLocManufacturer")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser.permission_sets.add(permission_set)

        now = timezone.now()
        device_id = "423e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestMissingLocManufacturer",
            "owner_id": "owner_missing_loc",
            "mfr_set_id": "SET_MISSING_LOC",
            "deployment_type": "single",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id,
                    "mfr_device_id": "mfr_missing_loc_device",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    # No location field at all
                    "recorded_at": now,
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
        assert serializer.is_valid(), serializer.errors

        subject, observations = BuoyService.process_gearset(serializer.validated_data, user=superuser)

        # Verify observation was created with EMPTY_POINT
        assert len(observations) == 1
        obs = observations[0]
        assert obs.location == EMPTY_POINT, f"Expected EMPTY_POINT, got {obs.location}"

        # Verify SubjectSource has null location
        subject_source = SubjectSource.objects.get(subject=subject)
        assert subject_source.location is None

    def test_trawl_with_mixed_location_devices(self, superuser):
        """Test trawl gearset where one device has location and another has null location."""

        # Create SubjectGroup and assign permission to superuser
        subject_group = SubjectGroup.objects.create(name="TestMixedLocManufacturer")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser.permission_sets.add(permission_set)

        now = timezone.now()
        device_id_with_loc = "523e4567-e89b-12d3-a456-426614174000"
        device_id_without_loc = "623e4567-e89b-12d3-a456-426614174000"
        data = {
            "manufacturer_name": "TestMixedLocManufacturer",
            "owner_id": "owner_mixed_loc",
            "mfr_set_id": "SET_MIXED_LOC",
            "deployment_type": "trawl",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id_with_loc,
                    "mfr_device_id": "mfr_with_loc",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 42.5, "longitude": -70.8},
                    "recorded_at": now,
                },
                {
                    "device_id": device_id_without_loc,
                    "mfr_device_id": "mfr_without_loc",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": None,
                    "recorded_at": now,
                },
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
        assert serializer.is_valid(), serializer.errors

        subject, observations = BuoyService.process_gearset(serializer.validated_data, user=superuser)

        # Verify both observations were created
        assert len(observations) == 2

        # Find observations by source
        obs_with_loc = next(o for o in observations if str(o.source.id) == device_id_with_loc)
        obs_without_loc = next(o for o in observations if str(o.source.id) == device_id_without_loc)

        # Verify locations
        assert obs_with_loc.location.x == -70.8  # longitude
        assert obs_with_loc.location.y == 42.5  # latitude
        assert obs_without_loc.location == EMPTY_POINT

        # Verify SubjectSource locations
        ss_with_loc = SubjectSource.objects.get(source_id=device_id_with_loc)
        ss_without_loc = SubjectSource.objects.get(source_id=device_id_without_loc)

        assert ss_with_loc.location is not None
        assert ss_with_loc.location.x == -70.8
        assert ss_with_loc.location.y == 42.5
        assert ss_without_loc.location is None

    def test_edgetech_format_location_with_null_lat_lon(self, superuser):
        """Test exact Edgetech payload format: location object with null latitude/longitude values.

        Edgetech sends: {"location": {"latitude": null, "longitude": null}}
        This is different from location: null or missing location field entirely.
        """

        # Create SubjectGroup and assign permission to superuser
        subject_group = SubjectGroup.objects.create(name="TestEdgetechManufacturer")
        permission_set, _ = PermissionSet.objects.get_or_create(name=subject_group.auto_permissionset_name)
        subject_group.permission_sets.add(permission_set)
        superuser.permission_sets.add(permission_set)

        now = timezone.now()
        device_id_with_loc = "723e4567-e89b-12d3-a456-426614174000"
        device_id_null_lat_lon = "823e4567-e89b-12d3-a456-426614174000"

        # Exact Edgetech format: one device has location, other has location object with null values
        data = {
            "manufacturer_name": "TestEdgetechManufacturer",
            "owner_id": "652e7174c0884e7f02ec97d1",
            "mfr_set_id": "SET_EDGETECH_FORMAT",
            "deployment_type": "trawl",
            "initial_deployment_date": now,
            "devices": [
                {
                    "device_id": device_id_with_loc,
                    "mfr_device_id": "88CE99D7C3_test",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    "location": {"latitude": 40.6014382, "longitude": -70.5142263},
                    "recorded_at": now,
                },
                {
                    "device_id": device_id_null_lat_lon,
                    "mfr_device_id": "88CE99D9A9_test",
                    "last_deployed": now,
                    "last_updated": now,
                    "device_status": "deployed",
                    # Exact Edgetech format: location object exists but lat/lon are null
                    "location": {"latitude": None, "longitude": None},
                    "recorded_at": now,
                },
            ],
        }

        serializer = GearCreateSerializer(data=data, context={"request": _create_mock_request(superuser)})
        assert serializer.is_valid(), serializer.errors

        subject, observations = BuoyService.process_gearset(serializer.validated_data, user=superuser)

        # Verify both observations were created
        assert len(observations) == 2

        # Find observations by source
        obs_with_loc = next(o for o in observations if str(o.source.id) == device_id_with_loc)
        obs_null_lat_lon = next(o for o in observations if str(o.source.id) == device_id_null_lat_lon)

        # Device with valid location should have real coordinates
        assert obs_with_loc.location.x == -70.5142263  # longitude
        assert obs_with_loc.location.y == 40.6014382  # latitude

        # Device with null lat/lon in location object should have EMPTY_POINT
        assert obs_null_lat_lon.location == EMPTY_POINT

        # Verify SubjectSource locations
        ss_with_loc = SubjectSource.objects.get(source_id=device_id_with_loc)
        ss_null_lat_lon = SubjectSource.objects.get(source_id=device_id_null_lat_lon)

        assert ss_with_loc.location is not None
        assert ss_with_loc.location.x == -70.5142263
        assert ss_with_loc.location.y == 40.6014382
        assert ss_null_lat_lon.location is None
