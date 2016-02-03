# import threading
# from das_server import pubsub
#
# def test_update_loop():
#     pubsub.publish({'source_id': 'b3850ad5-f7dc-4ad6-9ed8-5bd09dcc6a5a'}, 'das.tracking.source.observations.new')
#     threading.Timer(5.0, test_update_loop, []).start()
#
# started = False
# if not started:
#     started = True
#     threading.Timer(5.0, test_update_loop, []).start()