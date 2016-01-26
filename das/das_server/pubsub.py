"""
message publishing module
"""

import logging
import re
from importlib import import_module

from django.utils.module_loading import module_has_submodule
from kombu import Consumer, Connection, Exchange, Queue
from kombu.utils import nested

from das_server.celery_settings import BROKER_URL

logger = logging.getLogger(__name__)

das_exchange = Exchange('das', type='topic', durable=True)
connection = Connection(BROKER_URL)
pool = connection.Pool(20)

def publish(message, routing_key='das'):
    """Broadcast a message.

    :param message: JSONifyable message to send
    :param routing_key: routing key for the message. defaults to 'das'
        routing key is used in the topic exchange, so must be a list of words
        delimited by dots, up to the limit of 255 characters. Should begin
        with the string 'das'

        Example routing keys:
            das.event.analyzer.error
            das.tracking.data_input

    """

    # noinspection PyBroadException
    try:
        logger.debug('publish received message: {}  routing_key: {}'.format(message, routing_key))

        with pool.acquire() as conn:

            producer = conn.Producer(exchange=das_exchange)
            producer.publish(message, routing_key=routing_key)

    except Exception:
        logger.exception("Unhandled exception during publish")


def subscribe(routing_key='das.#', callback=None):
    """Subscribe to messages routed by routing_key

    :param routing_key: routing key for the message. defaults to 'das.#'
        routing key is used in the topic exchange, so must be a list of words
        delimited by dots, up to the limit of 255 characters. Should begin
        with the string 'das'

    :param callback: function to call on message.  Signature should be

    """
    # See das_server/management/commands/message_queue_listeners.py for the message
    # listener process.  It will be nice to be able to dynamically attach
    # subscriptions in there.
    raise NotImplementedError




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
DEFAULT_MESSAGE_QUEUE_MAP = (
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

    # TODO: I want to iterate over installed-apps to find the pubsub modules, but face some failures in testing.
    for app in ('analyzers', 'data_input', 'activity'): #settings.INSTALLED_APPS:
        if re.match(ignore_re, app):
            continue
        app_module = import_module(app)
        try:
            mn = "{}.{}".format(app, submodule)
            app_submodule = import_module(mn)
            if hasattr(app_submodule, 'PUBSUB_SUBSCRIPTIONS'):
                yield from app_submodule.PUBSUB_SUBSCRIPTIONS

        except Exception as e:
            if module_has_submodule(app_module, submodule):
                raise


def load_message_queue_mappings():
    '''
    Load (routing_key, callback) tuples for sibling applications.
    :return:
    '''
    return DEFAULT_MESSAGE_QUEUE_MAP + tuple(installed_apps_subscriptions())

def start_message_queue_listeners():

    # configure key / handler mapping somewhere less deep
    with Connection(BROKER_URL) as conn:

        consumers = []

        for routing_key, callback in load_message_queue_mappings():

            queue = Queue(
                channel=conn,
                exchange=das_exchange,
                routing_key=routing_key,
                no_ack=True,
                auto_delete=True
            )
            consumer = Consumer(conn, queues=[queue], callbacks=[callback])
            consumers.append(consumer)

        with nested(*consumers):
            while True:
                conn.drain_events()

