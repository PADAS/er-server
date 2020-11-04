import logging

from das_server import tasks

logger = logging.getLogger(__name__)


def new_event_handler(body, message):
    event_id = body.get('event_id')
    # tasks.queue_event_alert(event_id)
    logger.info('Heard new-event for event_id: %s', event_id)



def update_event_handler(body, message):
    event_id = body.get('event_id')
    # tasks.queue_event_alert(event_id)
    logger.info('Heard update-event for event_id: %s', event_id)


def new_patrol_handler(body, message):
    logger.info('Heard new-patrol for patrol_id: %s', body.get('patrol_id'))


def update_patrol_handler(body, message):
    logger.info('Heard update-patrol for patrol_id: %s', body.get('patrol_id'))


# Define the mapping between routing_keys and callbacks
# This will get picked up in pubsub.start_message_queue_listeners
PUBSUB_SUBSCRIPTIONS = (
    ('das.event.new', new_event_handler,
     'das_server.{0}'.format(new_event_handler.__name__)),
    ('das.event.update', update_event_handler,
     'das_server.{0}'.format(update_event_handler.__name__)),

    # patrol subscriptions
    ('das.patrol.new', new_patrol_handler,
     'das_server.{0}'.format(new_patrol_handler.__name__)),
    ('das.patrol.update', update_patrol_handler,
     'das_server.{0}'.format(update_patrol_handler.__name__)),
)
