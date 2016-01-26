import logging

from das_server import celery


logger = logging.getLogger(__name__)

def new_observations_callback(body, message):

    logger.debug('Received message [{}]. sending task analyzers.tasks.handle_source'.format(message))
    source_id = body['source_id']
    celery.app.send_task('analyzers.tasks.handle_source', args=(source_id,))


PUBSUB_SUBSCRIPTIONS = (
    ('das.tracking.source.observations.new', new_observations_callback),
)
