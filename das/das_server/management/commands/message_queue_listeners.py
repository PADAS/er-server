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

from importlib import import_module
from django.utils.module_loading import module_has_submodule
import re

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

def installed_apps_subscriptions(submodule='pubsub_registry', ignore_re='(djgeojson|django)'):
    '''
    Automatically import {{ app_name }}.pubsub_registry modules.
    :param submodules: module name(s) within INSTALLED_APPS.
    :param ignore_re: an re to ignore installed apps by pattern.
    :return: a generator of tuples representing subcriptions.
    '''
    for app in ('analyzers', 'data_input', 'activity'): #settings.INSTALLED_APPS:
        if re.match(ignore_re, app):
            continue
        _ = import_module(app)
        try:
            mn = "{}.{}".format(app, submodule)
            app_submodule = import_module(mn)
            if hasattr(app_submodule, 'PUBSUB_SUBSCRIPTIONS'):
                yield from app_submodule.PUBSUB_SUBSCRIPTIONS

        except Exception as e:
            if module_has_submodule(_, submodule):
                raise


def load_message_queue_mappings():
    return message_queue_mappings + tuple(installed_apps_subscriptions())

# message_queue_mappings = message_queue_mappings + load_installed_apps_pubsub()
# Now do the actual work of creating a queue for each mapping,
# attached to the exchange, then listen for messages forever
class Command(BaseCommand):

    help = 'routes messages on the message queue to handlers'

    def handle(self, *args, **options):

        # configure key / handler mapping somewhere less deep
        with Connection(BROKER_URL) as conn:

            consumers = []

            _ = load_message_queue_mappings()
            for routing_key, callback in _:

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

