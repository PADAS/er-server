import json
import random
from datetime import datetime, timezone

from factory import fuzzy
from geopy import Point
from geopy.distance import distance
    

def generate_devices(quantity: int, starting_point: Point = None):
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

    original_point = starting_point if starting_point else Point(random.uniform(-90, 90), random.uniform(-180, 180))
    return {"devices": [generate_device(original_point) for _ in range(quantity)]}