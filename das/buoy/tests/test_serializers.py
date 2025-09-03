import json

import pytest
from dateutil import parser as date_parser

from django.contrib.gis.geos import Point
from django.utils import timezone

from buoy.consts import BUOY_SUBJECT_SUBTYPE
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
            value=BUOY_SUBJECT_SUBTYPE, display="Ropeless Buoy Gearset", subject_type=subject_type
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
