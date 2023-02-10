import logging
import logging.config
import sys

import environ

try:
    # local_log.py should contain an override of DEFAULT_LOGGING as seen below
    from . import local_log
except ImportError:
    local_log = None

logger = logging.getLogger(__name__)

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

environ.Env.read_env()


DEFAULT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": "%(asctime)s %(levelname)s %(processName)s %(thread)d %(name)s %(message)s",
            "class": "utils.log.CloudLogsJsonFormatter",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "stream": sys.stdout, "formatter": "json"},
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "propagate": False,
            "level": env.str("DJANGO_LOGGING_LEVEL", "INFO"),
        },
        "django.request": {
            "handlers": ["console"],
            "propagate": False,
            "level": env.str("DJANGO_REQUEST_LOGGING_LEVEL", "INFO"),
        },
        "django.server": {
            "handlers": ["console"],
            "propagate": False,
            "level": env.str("DJANGO_SERVER_LOGGING_LEVEL", "INFO"),
        },
        "rt_api": {
            "level": env.str("RTAPI_LOGGING_LEVEL", "WARNING"),
        },
        "rt_api.socketio": {
            "level": env.str("RTAPI_SOCKET_LOGGING_LEVEL", "WARNING"),
        },
        "rt_api.pubsub_listener": {
            "level": env.str("RTAPI_PUBSUB_LOGGING_LEVEL", "WARNING"),
        },
        "": {
            "handlers": ["console"],
            "level": env.str("ROOT_LOGGING_LEVEL", "WARNING"),
        },
        "PIL.Image": {
            "level": "WARNING",
        },
        "datadog.dogstatsd": {"level": "ERROR"},
    },
}


has_initialized = False


def init_logging(service="default_logging"):
    global has_initialized

    if has_initialized:
        logger.debug("logging already initialized, not loading %s", service, exc_info=True)
        return

    has_initialized = True

    try:
        module = sys.modules[__name__]
        if local_log:
            module = local_log
        log_settings = getattr(module, service.upper())
    except AttributeError:
        message = "No logging configuration" " found for {0} in {1}".format(service, repr(module))
        logger.warning(message)
        raise KeyError(message)
    logging.config.dictConfig(log_settings)
