import pytest
from dateutil import parser as date_parser

from das.buoy.serializers import GearSerializer
from utils.tenant.dataclass import FeatureFlags
from das.buoy.tests import generate_devices


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.skipif(FeatureFlags.buoy_api_enabled is False, reason="Buoy API feature flag is off")
class TestGearSerializer:
    def test_with_trawl_gear_subject(self, gear_subject):
        gear_subject.additional = generate_devices(2)
        gear_subject.save()

        serialized_gear = GearSerializer(gear_subject).data

        assert serialized_gear["id"] == str(gear_subject.id)
        assert serialized_gear["display_id"] == gear_subject.name
        assert serialized_gear["state"] in ("deployed", "hauled")
        if serialized_gear["state"] == "deployed":
            assert gear_subject.is_active
        else:
            assert not gear_subject.is_active

        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] in ("trawl", "single")
        assert serialized_gear["devices"] == gear_subject.additional["devices"]
        assert len(serialized_gear["devices"]) == 2

    def test_with_single_gear_subject(self, gear_subject):
        gear_subject.additional = generate_devices(1)
        gear_subject.save()

        serialized_gear = GearSerializer(gear_subject).data

        assert serialized_gear["id"] == str(gear_subject.id)
        assert serialized_gear["display_id"] == gear_subject.name

        assert serialized_gear["state"] in ("deployed", "hauled")
        if serialized_gear["state"] == "deployed":
            assert gear_subject.is_active
        else:
            assert not gear_subject.is_active

        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] == "single"
        assert serialized_gear["devices"] == gear_subject.additional["devices"]
        assert len(serialized_gear["devices"]) == 1
