import logging

from das_server import pubsub


logger = logging.getLogger(__name__)


def notify_new_tracks(source_id):
    '''Notify of new observations for the given source.'''
    try:
        pubsub.publish({'source_id': str(source_id)}, 'das.tracking.source.observations.new')
        return True

    except Exception:
        logger.exception('Exception while publishing message.')
