""" routes messages on the message queue to handlers
all routing_key -> handler mapping currently is defined
in here, you may want to make this more flexible
"""

import logging

from django.core.management.base import BaseCommand
from kombu import Consumer, Connection, Exchange, Queue
from kombu.utils import nested

from das_server import pubsub
from das_server.celery_settings import BROKER_URL


logger = logging.getLogger(__name__)

# Here are some sample callbacks, followed by mappings to them.
def event_callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "event_callback message: {} body: {}".format(message, body)
    print(msg)

def another_event_callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "another_event_callback message: {} body: {}".format(message, body)
    print(msg)

def tracking_callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "tracking_callback message: {} body: {}".format(message, body)
    print(msg)

# Now define the mapping between routing_keys and callbacks
message_queue_mappings = (
    ('das.event.#', event_callback),
    ('das.event.#', another_event_callback),
    ('das.tracking.#', tracking_callback)
)

# Now do the actual work of creating a queue for each mapping,
# attached to the exchange, then listen for messages forever
class Command(BaseCommand):

    help = 'routes messages on the message queue to handlers'

    def handle(self, *args, **options):

        # configure key / handler mapping somewhere less deep
        with Connection(BROKER_URL) as conn:

            consumers = []

            for routing_key, callback in message_queue_mappings:

                queue = Queue(
                    channel=conn,
                    exchange=pubsub.das_exchange,
                    routing_key=routing_key,
                    no_ack=True,
                    auto_delete=True
                )
                consumer = Consumer(conn, queues=[queue], callbacks=[callback])
                consumers.append(consumer)

            with nested(*consumers):
                while True:
                    conn.drain_events()

