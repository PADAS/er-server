import json
import random
from datetime import datetime, timezone

from django.utils import timezone
from factory import fuzzy
from factories import GearFactory
from django.contrib.gis.geos import Point
from geopy.distance import distance
from observations.models import Observation
    

TEST_LOCATION = Point(0, 0)

def get_custom_location_gear_subjectsource(location: Point = TEST_LOCATION):
        gear_subjectsource = GearFactory.create()
        gear_subjectsource.save()

        source = gear_subjectsource.source
        now = timezone.now()
        additional = generate_devices(2, location)
        data = {
            "recorded_at": now,
            "location": location,
            "source": source,
            "additional": additional,
        }
       
        observation = Observation.objects.create(**data)
        observation.save()

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
        "display_id": fuzzy.FuzzyText(length=12).evaluate(1, 1, None).__str__(),
    }
