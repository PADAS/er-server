import logging

from das_server import celery


logger = logging.getLogger(__name__)


def new_observations_callback(body, message):

    logger.debug(
        'new observation message [%s], sending task analyzers.tasks.handle_observation', str(body))
    celery.app.send_task(
        'analyzers.tasks.handle_observation', args=(body['id'],))


PUBSUB_SUBSCRIPTIONS = (
    ('das.tracking.source.observations.new', new_observations_callback,
     'analyzers.{0}'.format(new_observations_callback.__name__)),
)
