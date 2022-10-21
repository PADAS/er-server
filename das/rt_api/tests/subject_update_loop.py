import threading
from das_server import pubsub

interval = 15.0
count = 0

source_id = '2b63859b-a8b3-4c4e-914e-58c850ca00d1'
subject_id = '776e320a-bd92-48b5-9899-724105b7033c'
event_id = 'c570d6db-9d45-4db3-95ae-855d4cf562da'

def test_update_loop():
    global count
    count += 1
    count %= 5

    if count == 0:
        pubsub.publish({'source_id': source_id}, 'das.tracking.source.observations.new')
    elif count == 1:
        pubsub.publish({'subject_id': subject_id}, 'das.tracking.source.observations.new')
    elif count == 2:
        pubsub.publish({'event_id': event_id}, 'das.event.new')
    elif count == 3:
        pubsub.publish({'event_id': event_id}, 'das.event.update')
    else:
        pubsub.publish({'event_id': event_id}, 'das.event.delete')

    threading.Timer(interval, test_update_loop, []).start()

started = False
if not started:
    started = True
    threading.Timer(interval, test_update_loop, []).start()