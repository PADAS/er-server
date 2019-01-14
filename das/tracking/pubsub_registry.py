import logging

from das_server import pubsub


logger = logging.getLogger(__name__)


def notify_new_tracks(source_id):
    '''Notify of new observations for the given source.'''
    try:
        pubsub.publish({'source_id': str(source_id)},
                       'das.tracking.source.observations.new')
        return True

    except Exception:
        logger.exception(
            'Error publishing notify_new_tracks, source_id=%s', source_id)


def notify_subjectstatus_update(subject_id):
    '''Notify of updated subject status.'''
    try:
        pubsub.publish({'subject_id': str(subject_id)},
                       'das.subjectstatus.update')
    except Exception:
        logger.exception(
            'Error publishing notify_subjectstatus_update, subject_id=%s', subject_id)


PUBSUB_SUBSCRIPTIONS = []
