import pytest
from dateutil import parser as date_parser

from das.buoy.serializers import GearSerializer


@pytest.mark.django_db
@pytest.mark.usefixtures("trawl_gear_subject", "single_gear_subject")
class TestGearSerializer:
    def test_with_trawl_gear_subject(self, trawl_gear_subject):
        trawl_gear_subject.save()

        serialized_gear = GearSerializer(trawl_gear_subject).data

        assert serialized_gear["id"] == str(trawl_gear_subject.id)
        assert serialized_gear["display_id"] == trawl_gear_subject.name
        assert serialized_gear["state"] in ("deployed", "hauled")
        if serialized_gear["state"] == "deployed":
            assert trawl_gear_subject.is_active
        else:
            assert not trawl_gear_subject.is_active

        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] in ("trawl", "single")
        assert serialized_gear["devices"] == trawl_gear_subject.additional["devices"]
        assert len(serialized_gear["devices"]) == 2

    def test_with_single_gear_subject(self, single_gear_subject):
        single_gear_subject.save()

        serialized_gear = GearSerializer(single_gear_subject).data

        assert serialized_gear["id"] == str(single_gear_subject.id)
        assert serialized_gear["display_id"] == single_gear_subject.name

        assert serialized_gear["state"] in ("deployed", "hauled")
        if serialized_gear["state"] == "deployed":
            assert single_gear_subject.is_active
        else:
            assert not single_gear_subject.is_active

        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] == "single"
        assert serialized_gear["devices"] == single_gear_subject.additional["devices"]
        assert len(serialized_gear["devices"]) == 1
