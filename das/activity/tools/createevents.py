import random

import django
django.setup()
from django.contrib.gis.geos import Point

from activity.models import Event, EventType

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
                  event_type=EventType.objects.get_by_value('other'),
                  priority=Event.PRI_IMPORTANT,
                  provenance=Event.PC_SYSTEM,
                  attributes={},
                  location=gen_random_point()
                  )
        )

    for event in newevents:
        event.save()

except Exception as e:
    print(e)






