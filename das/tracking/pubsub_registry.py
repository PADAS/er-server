import logging

logger = logging.getLogger(__name__)
from das_server import pubsub

def tracking_callback(body, message):
    logger.debug('Received message [{}].'.format(message))


PUBSUB_SUBSCRIPTIONS = (
    ('das.#', tracking_callback),
)

def notify_new_tracks(source_id):
    '''Notify of new observations for the given source.'''
    try:
        pubsub.publish({'source_id': str(source_id)}, 'das.tracking.source.observations.new')
    except Exception:
        logger.exception('Exception while publishing message.')
    return True
