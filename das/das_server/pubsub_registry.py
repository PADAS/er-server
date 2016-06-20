import logging

from das_server import tasks

logger = logging.getLogger(__name__)

def event_mailer(body, message):
    """ gets event mailed """
    msg = "event_mailer message: {} body: {}".format(message.delivery_info, body)
    logger.info(msg)
    event_id = body.get('event_id')
    tasks.event_mailer.delay(event_id)

# Here are some sample callbacks, followed by mappings to them.
def event_callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "event_callback message: {} body: {}".format(message.delivery_info, body)
    logger.debug(msg)

def tracking_callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "tracking_callback message: {} body: {}".format(message.delivery_info, body)
    logger.debug(msg)


# Now define the mapping between routing_keys and callbacks
# This will get picked up in pubsub.start_message_queue_listeners
PUBSUB_SUBSCRIPTIONS = (
    ('das.event.new', event_mailer, 'das_server.{0}'.format(event_mailer.__name__)),
    ('das.event.#', event_callback, 'das_server.{0}'.format(event_callback.__name__)),
    ('das.tracking.#', tracking_callback, 'das_server.{0}'.format(tracking_callback.__name__))
)
