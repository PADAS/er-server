import django
django.setup()
from django.contrib.gis.geos import Point
import random
import datetime
import pytz
from functools import namedtuple

import observations
from activity.models import Event

def gen_random_point():
    # Generate random point within Vulcan PA.
    lon = float(random.random() * 5.0 + 24.5 )
    lat = float(random.random() * 7.0 + 21.5)

    return Point(lon, lat)

try:

    newevents = []


    for x in range(0,100):
        newevents.append(
            Event(message='Test event {}'.format(x),
                  event_type=Event.ET_SYSTEM,
                  priority=Event.PRI_IMPORTANT,
                  provenance=Event.INFORMANT,
                  attributes={},
                  location=gen_random_point()
                  )
        )

    Event.objects.bulk_create(newevents)

except Exception as e:
    print(e)






