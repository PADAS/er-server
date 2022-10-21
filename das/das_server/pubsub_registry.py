import logging

from das_server import tasks

logger = logging.getLogger(__name__)


def new_event_handler(body, message):
    event_id = body.get('event_id')
    logger.info('Heard new-event for event_id: %s', event_id)


def update_event_handler(body, message):
    event_id = body.get('event_id')
    logger.info('Heard update-event for event_id: %s', event_id)


def delete_event_handler(body, message):
    event_id = body.get('event_id')
    logger.info('Heard delete-event for event_id: %s', event_id)


def new_patrol_handler(body, message):
    logger.info('Heard new-patrol for patrol_id: %s', body.get('patrol_id'))


def update_patrol_handler(body, message):
    logger.info('Heard update-patrol for patrol_id: %s', body.get('patrol_id'))


def delete_patrol_handler(body, message):
    logger.info('Heard delete-patrol for patrol_id: %s', body.get('patrol_id'))


def new_message_handler(body, message):
    logger.info('Heard a new message id: %s', body.get('message_id'))


def update_message_handler(body, message):
    logger.info('Heard a update-message id: %s', body.get('message_id'))


def delete_message_handler(body, message):
    logger.info('Heard a delete-message id: %s', body.get('message_id'))


def new_announcement_handler(body, message):
    logger.info('Heard a new message id: %s', body.get('announcement_id'))


# Define the mapping between routing_keys and callbacks
# This will get picked up in pubsub.start_message_queue_listeners
PUBSUB_SUBSCRIPTIONS = (
    ('das.event.new', new_event_handler,
     'das_server.{0}'.format(new_event_handler.__name__)),
    ('das.event.update', update_event_handler,
     'das_server.{0}'.format(update_event_handler.__name__)),
    ('das.event.delete', delete_event_handler,
     'das_server.{0}'.format(delete_event_handler.__name__)),

    # patrol subscriptions
    ('das.patrol.new', new_patrol_handler,
     'das_server.{0}'.format(new_patrol_handler.__name__)),
    ('das.patrol.update', update_patrol_handler,
     'das_server.{0}'.format(update_patrol_handler.__name__)),
    ('das.patrol.delete', delete_patrol_handler,
     'das_server.{0}'.format(delete_patrol_handler.__name__)),

    # message subscriptions
    ('das.message.new', new_message_handler,
     'das_server.{0}'.format(new_message_handler.__name__)),
    ('das.message.update', update_message_handler,
     'das_server.{0}'.format(update_message_handler.__name__)),
    ('das.message.delete', delete_message_handler,
     'das_server.{0}'.format(delete_message_handler.__name__)),

    # announcement subscriptions
    ('das.announcement.new', new_announcement_handler,
     'das_server.{0}'.format(new_announcement_handler.__name__)),
)
