import json
import random
from datetime import datetime, timezone

from factory import fuzzy
from geopy.distance import distance

from django.contrib.gis.geos import Point

from factories import GearFactory
from observations.models import Observation, SubjectSubType, SubjectType

TEST_LOCATION = Point(0, 0)


def get_custom_location_gear_subjectsource(location: Point = TEST_LOCATION):
    gear_subjectsource = GearFactory.create()

    subject_type, _ = SubjectType.objects.get_or_create(value="gear", defaults={"display": "Gear"})
    subject_subtype, _ = SubjectSubType.objects.get_or_create(
        value="ropeless_buoy_device", defaults={"display": "Ropeless Buoy Device", "subject_type": subject_type}
    )
    gear_subjectsource.subject.subject_subtype = subject_subtype
    gear_subjectsource.subject.is_active = True

    source = gear_subjectsource.source
    now = datetime.now(tz=timezone.utc)
    additional = generate_devices(2, location)
    data = {
        "recorded_at": now,
        "location": location,
        "source": source,
        "additional": additional,
    }

    observation = Observation.objects.create(**data)
    observation.save()

    gear_subjectsource.subject.additional = additional
    gear_subjectsource.subject.save()

    return gear_subjectsource


def generate_devices(quantity: int, starting_point: Point = TEST_LOCATION):
    def generate_point_nearby(original_point, miles):
        bearing = random.uniform(0, 360)
        new_point = distance(miles=miles).destination(original_point, bearing)
        return {"latitude": new_point.latitude, "longitude": new_point.longitude}

    def generate_device(original_point):
        device = dict()
        device["device_id"] = fuzzy.FuzzyText(length=10, prefix="device_").evaluate(1, 1, None).__str__()
        device["last_updated"] = str(datetime.now(tz=timezone.utc))
        device["location"] = generate_point_nearby(original_point, 5)
        device["label"] = fuzzy.FuzzyText(length=1).evaluate(1, 1, None).__str__()
        return json.dumps(device)

    original_point = Point(random.uniform(-90, 90), random.uniform(-180, 180))
    return {
        "devices": [generate_device(original_point) for _ in range(quantity)],
        "display_id": generate_fake_display_id(),
    }


def generate_fake_display_id():
    return fuzzy.FuzzyText(length=12).evaluate(1, 1, None).__str__()
