import threading
from das_server import pubsub

count = 0

def test_update_loop():
    global count
    count += 1
    if count % 2 == 0:
        pubsub.publish({'source_id': 'b3850ad5-f7dc-4ad6-9ed8-5bd09dcc6a5a'}, 'das.tracking.source.observations.new')
    else:
        pubsub.publish({'event_id': '4eabc0dc-f5b8-4701-bfb7-b56b99e4f35f'}, 'das.event.new')
    threading.Timer(5.0, test_update_loop, []).start()

started = False
if not started:
    started = True
    threading.Timer(5.0, test_update_loop, []).start()