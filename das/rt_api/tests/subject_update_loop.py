import threading
from das_server import pubsub

def test_update_loop():
    pubsub.publish({'source_id': 'c3f080a6-44b9-4fa7-bb3e-6e62285c040c'}, 'das.tracking.update')
    threading.Timer(5.0, test_update_loop, []).start()


threading.Timer(5.0, test_update_loop, []).start()