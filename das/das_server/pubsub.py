"""
message publishing module
"""

import logging

from kombu import Connection, Exchange, Queue

from das_server.celery_settings import BROKER_URL


logger = logging.getLogger(__name__)

das_exchange = Exchange('das', type='topic', durable=True)


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

        with Connection(BROKER_URL) as conn:

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
