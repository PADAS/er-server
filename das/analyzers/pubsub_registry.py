import logging

from das_server import celery
from utils.features import features
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)


def new_observations_callback(body, message):
    logger.debug("new source observation message [%s], sending task analyzers.tasks.handle_source", str(body))

    celery.app.send_task(
        "analyzers.tasks.handle_source",
        args=(body["source_id"],),
        kwargs={"domain": get_tenant_settings().domain} if features.tms.is_on() else {},
    )


PUBSUB_SUBSCRIPTIONS = (
    (
        "das.tracking.source.observations.new",
        new_observations_callback,
        f"analyzers.{new_observations_callback.__name__}",
    ),
)
