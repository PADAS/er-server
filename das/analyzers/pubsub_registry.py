import logging

from das_server import celery


logger = logging.getLogger(__name__)


def new_observations_callback(body, message):

    logger.debug('new observation message [{}].'
                 ' sending task analyzers.tasks.handle_source'.format(body))
    source_id = body['source_id']
    celery.app.send_task('analyzers.tasks.handle_source', args=(source_id,))


PUBSUB_SUBSCRIPTIONS = (
    ('das.tracking.source.observations.new', new_observations_callback,
     'analyzers.{0}'.format(new_observations_callback.__name__)),
)
