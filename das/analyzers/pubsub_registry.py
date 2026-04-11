import logging

from analyzers.tasks import handle_source

logger = logging.getLogger(__name__)


def new_observations_callback(body, message):
    logger.debug("new source observation message [%s], sending task analyzers.tasks.handle_source", str(body))
    handle_source.apply_async(args=(body["source_id"],))


PUBSUB_SUBSCRIPTIONS = (
    (
        "das.tracking.source.observations.new",
        new_observations_callback,
        f"analyzers.{new_observations_callback.__name__}",
    ),
)
