"""
message publishing module
"""

import logging

from kombu import Connection, Exchange

from das_server import celery_settings


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

        with Connection(celery_settings.BROKER_URL) as conn:

            producer = conn.Producer()
            producer.publish(message, exchange=das_exchange, routing_key=routing_key)

    except Exception:
        logger.exception("Unhandled exception during publish")
