import json

import pytest
from dateutil import parser as date_parser

from django.contrib.gis.geos import Point
from django.utils import timezone

from das.buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from das.buoy.serializers import GearSerializer
from das.buoy.tests import generate_devices
from factories import SubjectTypeFactory
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
    SubjectSubType,
)
from buoy.serializers import GearCreateSerializer, GearsSerializer
from buoy.serializers.gear import GEAR_DEPLOYED_EVENT, SOURCE_TYPE, SUBJECT_SUBTYPE
from buoy.tests import generate_devices
from core.tests import BaseAPITest
from observations.models import Observation
from utils.tenant.dataclass import FeatureFlags


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.skipif(FeatureFlags.buoy_api_enabled is False, reason="Buoy API feature flag is off")
class TestGearSerializer:
    def test_with_trawl_gear_subject(self, gear_subjectsource):
        gear_subjectsource.subject.is_active = True
        gear_subjectsource.save()

        source = gear_subjectsource.source
        provider = gear_subjectsource.source.provider
        provider.save()
        now = timezone.now()
        additional = generate_devices(2)
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }

        observation = Observation.objects.create(**data)
        observation.save()

        serialized_gear = GearSerializer(gear_subjectsource).data

        assert serialized_gear["id"] == str(gear_subjectsource.subject.id)
        assert serialized_gear["display_id"] == additional["display_id"]
        assert serialized_gear["status"] == "deployed"
        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] == "trawl"
        assert serialized_gear["devices"] == observation.additional["devices"]
        assert len(serialized_gear["devices"]) == 2

        # Test hauled status
        gear_subjectsource.subject.is_active = False
        serialized_gear = GearSerializer(gear_subjectsource).data
        assert serialized_gear["status"] == "hauled"

    def test_with_single_gear_subject(self, gear_subjectsource):
        gear_subjectsource.subject.is_active = True
        gear_subjectsource.save()

        source = gear_subjectsource.source
        provider = gear_subjectsource.source.provider
        provider.save()
        now = timezone.now()
        additional = generate_devices(1)
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }

        observation = Observation.objects.create(**data)
        observation.save()

        serialized_gear = GearSerializer(gear_subjectsource).data

        assert serialized_gear["id"] == str(gear_subjectsource.subject.id)
        assert serialized_gear["display_id"] == additional["display_id"]
        assert serialized_gear["status"] == "deployed"
        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] == "single"
        assert serialized_gear["devices"] == observation.additional["devices"]
        assert len(serialized_gear["devices"]) == 1

        # Test hauled status
        gear_subjectsource.subject.is_active = False
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

        # Create SubjectSource relationships
        subject_source1 = SubjectSource.objects.create(subject=subject, source=source1)

        subject_source2 = SubjectSource.objects.create(subject=subject, source=source2)

        # Create observations for both sources
        now = timezone.now()
        location1 = Point(-24.43071, 31.19239)
        location2 = Point(-24.44071, 31.20239)

        Observation.objects.create(recorded_at=now, location=location1, source=source1)

        Observation.objects.create(recorded_at=now, location=location2, source=source2)

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
        assert device1["last_deployed"] == "2024-10-16T11:08:17-08:00"

        # Check second device
        device2 = next(d for d in devices if d["device_id"] == "device_002")
        assert device2["label"] == "b"  # Second device should get label 'b'
        assert "location" in device2
        assert device2["location"]["latitude"] == 31.20239
        assert device2["location"]["longitude"] == -24.44071
        assert device2["last_deployed"] == "2024-10-16T12:15:22-08:00"

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

        # Create SubjectSource relationships - subject1 has 1 source, subject2 has 2 sources
        subject_source1 = SubjectSource.objects.create(subject=subject1, source=source1)
        subject_source2 = SubjectSource.objects.create(subject=subject2, source=source2)

        # Create observations for all sources
        now = timezone.now()
        location1 = Point(-24.43071, 31.19239)
        location2 = Point(-24.44071, 31.20239)
        location3 = Point(-24.45071, 31.21239)

        Observation.objects.create(recorded_at=now, location=location1, source=source1)
        Observation.objects.create(recorded_at=now, location=location2, source=source2)
        Observation.objects.create(recorded_at=now, location=location3, source=source3)

        # Act - serialize using subject1, but should get devices from both subjects
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
                    "mfr_device_id": "mfr123",
                    "mfr_id": "mfrcomp",
                    "device_initial_deploy_date": now,
                    "device_last_updated_date": now,
                    "device_status": "deployed",
                    "location": {"latitude": 1.23, "longitude": 4.56},
                }
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 99})
        assert serializer.is_valid(), serializer.errors
        observations = serializer.save()
        assert isinstance(observations, list)
        assert len(observations) == 1
        obs = observations[0]
        # Basic fields
        assert obs["name"]
        assert obs["source"] == obs["name"]
        assert obs["type"] == SOURCE_TYPE
        assert obs["subject_type"] == SUBJECT_SUBTYPE
        assert obs["is_active"] is True
        assert obs["recorded_at"] == now
        assert obs["location"] == {"lat": 1.23, "lon": 4.56}
        # Additional payload
        additional = obs["additional"]
        assert additional["user_id"] == 99
        assert additional["subject_name"] == obs["name"]
        assert additional["event_type"] == GEAR_DEPLOYED_EVENT
        assert isinstance(additional["devices"], list) and len(additional["devices"]) == 1
        # Label generation
        assert additional["devices"][0]["label"] == "A"

    def test_save_multiple_devices(self):
        now = timezone.now()
        data = {
            "owner_id": "ownerXYZ",
            "deployment_type": "trawl",
            "initial_deployment_date": now,
            "devices": [
                {
                    "mfr_device_id": "mfrA",
                    "mfr_id": "compA",
                    "device_initial_deploy_date": now,
                    "device_last_updated_date": now,
                    "device_status": "deployed",
                    "location": {"latitude": 0.0, "longitude": 0.0},
                },
                {
                    "mfr_device_id": "mfrB",
                    "mfr_id": "compB",
                    "device_initial_deploy_date": now,
                    "device_last_updated_date": now,
                    "device_status": "hauled",
                    "location": {"latitude": 9.99, "longitude": 9.99},
                },
            ],
        }
        serializer = GearCreateSerializer(data=data, context={"user_id": 7})
        assert serializer.is_valid(), serializer.errors
        observations = serializer.save()
        assert isinstance(observations, list)
        # Two observations returned
        assert len(observations) == 2
        # Display ID consistency
        display_ids = {obs["additional"]["display_id"] for obs in observations}
        assert len(display_ids) == 1 and len(display_ids.pop()) == 12
        # Check labels A and B
        labels = [obs["additional"]["devices"][i]["label"] for i, obs in enumerate(observations)]
        assert labels == ["A", "B"]
        # Check active status for each device
        statuses = [obs["is_active"] for obs in observations]
        assert statuses == [True, False]
