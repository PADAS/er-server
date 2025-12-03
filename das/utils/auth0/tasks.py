import logging

from celery_once import QueueOnce

from das_server import celery
from utils.auth0.auth0_validators import Auth0JWTBearerTokenValidator

logger = logging.getLogger(__name__)


@celery.app.task(base=QueueOnce, once={"graceful": True, "timeout": 60})
def refresh_cached_auth0_jwks() -> None:
    try:
        Auth0JWTBearerTokenValidator().force_jwks_cache_refresh()
    except Exception as ex:
        logger.warning("Failed to refresh cached Auth0 JWKS: %s", ex)
        raise
