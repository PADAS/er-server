import json
import random
from datetime import datetime, timezone

import pytest
from dateutil import parser as date_parser
from factory import fuzzy
from geopy import Point
from geopy.distance import distance

from das.buoy.serializers import GearSerializer
from utils.features import features


def generate_devices(quantity: int):
    def generate_point_nearby(original_point, miles):
        bearing = random.uniform(0, 360)
        new_point = distance(miles=miles).destination(original_point, bearing)
        return {"latitude": new_point.latitude, "longitude": new_point.longitude}

    def generate_device(original_point):
        device = dict()
        device["name"] = fuzzy.FuzzyText(length=10, prefix="device_").evaluate(1, 1, None).__str__()
        device["updated_at"] = str(datetime.now(tz=timezone.utc))
        device["location"] = generate_point_nearby(original_point, 5)
        device["label"] = fuzzy.FuzzyText(length=1).evaluate(1, 1, None).__str__()
        return json.dumps(device)

    original_point = Point(random.uniform(-90, 90), random.uniform(-180, 180))
    return {"devices": [generate_device(original_point) for _ in range(quantity)]}


@pytest.mark.django_db
@pytest.mark.usefixtures("gear_subject")
@pytest.mark.skipif(features.buoy_api_enabled.is_on() is False, reason="Buoy API feature flag is off")
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
