import threading
from das_server import pubsub

interval = 30.0
count = 0

def test_update_loop():
    global count
    count += 1
    if count % 2 == 0:
        pubsub.publish({'subject_id': '254fb6ef-d8f3-40ef-806b-ebecfb92913d'}, 'das.tracking.source.observations.new')
    else:
        pubsub.publish({'event_id': '4eabc0dc-f5b8-4701-bfb7-b56b99e4f35f'}, 'das.event.new')
    threading.Timer(interval, test_update_loop, []).start()

started = False
if not started:
    started = True
    threading.Timer(interval, test_update_loop, []).start()