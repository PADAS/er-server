import logging

from das_server import tasks

logger = logging.getLogger(__name__)


def new_event_handler(body, message):
    event_id = body.get('event_id')
    tasks.queue_event_alert(event_id)


def update_event_handler(body, message):
    event_id = body.get('event_id')
    tasks.queue_event_alert(event_id)


# Define the mapping between routing_keys and callbacks
# This will get picked up in pubsub.start_message_queue_listeners
PUBSUB_SUBSCRIPTIONS = (
    ('das.event.new', new_event_handler,
     'das_server.{0}'.format(new_event_handler.__name__)),
    ('das.event.update', update_event_handler,
     'das_server.{0}'.format(update_event_handler.__name__)),
)
