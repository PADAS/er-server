""" das_server.pubsub_registry
This is a demonstration of pubsub_registry patterns which logs events
"""

import logging


logger = logging.getLogger(__name__)


# Here are some sample callbacks, followed by mappings to them.
def event_callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "event_callback message: {} body: {}".format(message.delivery_info, body)
    logger.debug(msg)

def another_event_callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "another_event_callback message: {} body: {}".format(message, body)
    logger.debug(msg)

def tracking_callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "tracking_callback message: {} body: {}".format(message.delivery_info, body)
    logger.debug(msg)


# Now define the mapping between routing_keys and callbacks
# This will get picked up in pubsub.start_message_queue_listeners
PUBSUB_SUBSCRIPTIONS = (
    ('das.event.#', event_callback),
    ('das.event.#', another_event_callback),
    ('das.tracking.#', tracking_callback)
)
