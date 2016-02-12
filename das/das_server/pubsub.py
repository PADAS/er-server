"""
message publishing module
"""

from importlib import import_module
import logging
import re
import signal
import socket

from django.apps import apps
from django.utils.module_loading import module_has_submodule
from kombu import Consumer, Connection, Exchange, Queue
from kombu.utils import nested

from django.conf import settings


logger = logging.getLogger(__name__)

das_exchange = Exchange('das', type='topic', durable=True)
connection = Connection(settings.PUBSUB_BROKER_URL)
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


def subscribe(subscription_list, loop_forever=True):
    """Create a set of subscriptions to messages routed by routing_key

    :param subscription_list: a list of dictionaries with keys
        'routing_key' and 'callback'.

    routing_key is the routing key for the message. defaults to 'das.#'
        routing key is used in the topic exchange, so must be a list of words
        delimited by dots, up to the limit of 255 characters. Should begin
        with the string 'das'

    callback is the function to call on the message.

    This function will block, but can be run in a thread
    """

    with Connection(settings.PUBSUB_BROKER_URL) as conn:

        consumers = []

        for subscription in subscription_list:
            consumer = get_consumer(conn, subscription['routing_key'], subscription['callback'])
            consumers.append(consumer)

        with nested(*consumers):
            while True:
                conn.drain_events()
                if not loop_forever:
                    break


def installed_apps_subscriptions(submodule='pubsub_registry', ignore_re='(djgeojson|django)'):
    '''
    Automatically import {{ app_name }}.pubsub_registry modules.
    :param submodules: module name(s) within INSTALLED_APPS.
    :param ignore_re: an re to ignore installed apps by pattern.
    :return: a generator of tuples representing subcriptions.
    '''

    for app_config in apps.get_app_configs():
        if re.match(ignore_re, app_config.name):
            continue

        logger.debug('registering tasks for app {}'.format(app_config.name))
        module_name = "{}.{}".format(app_config.name, submodule)

        try:
            app_submodule = import_module(module_name)
            for routing_key, callback in app_submodule.PUBSUB_SUBSCRIPTIONS:
                logger.info('registering routing key {} to {}'.format(routing_key, callback.__name__))
                yield (routing_key, callback)

        except AttributeError as e:
            logger.warn('{}.PUBSUB_SUBSCRIPTIONS should be a sequence of (routing_key, callback) sequences'.format(module_name))
        except ImportError as e:
            logger.debug('No pubsub registrations imported for app {}'.format(app_config.name))


running = True
def signal_handler(*args):
    logger.warning("SIGINT caught")
    global running
    running = False

signal.signal(signal.SIGINT, signal_handler)


def get_consumer(connection, routing_key, callback):
    """ returns a kombu.Consumer which routes messages from connection
     with routing_key to callback """

    queue = Queue(
         channel=connection,
         exchange=das_exchange,
         routing_key=routing_key,
         no_ack=True,
         auto_delete=True
    )
    consumer = Consumer(connection, queues=[queue], callbacks=[callback])
    return consumer


def start_message_queue_listeners():

    with Connection(settings.PUBSUB_BROKER_URL) as conn:

        consumers = []

        for routing_key, callback in installed_apps_subscriptions():
            consumer = get_consumer(conn, routing_key, callback)
            consumers.append(consumer)

        with nested(*consumers):
            while running:
                try:
                    conn.drain_events(timeout=2)
                except socket.timeout as e:
                    logger.debug('No messages received for 2 seconds')

            logger.debug('Exiting')
