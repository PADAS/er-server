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


def update_level_in_log_config(config: dict, level: str) -> dict:

    loggers = config["loggers"]

    loggers[""]["level"] = level
    loggers["rt_api.socketio"]["level"] = level
    if level == "DEBUG":
        config["handlers"]["console"]["level"] = level
        loggers["django"]["level"] = level
        loggers["django.request"]["level"] = level
        loggers["django.server"]["level"] = level
        loggers["rt_api"]["level"] = level
        loggers["rt_api.pubsub_listener"]["level"] = level

    return config


def init_logging(service=None):
    global has_initialized

    if not service:
        service = "default_logging"

    if has_initialized:
        logger.debug("logging already initialized, not loading %s", service, exc_info=True)
        return

    has_initialized = True

    level = env.str("ROOT_LOGGING_LEVEL", "")

    try:
        module = sys.modules[__name__]
        if local_log:
            module = local_log
        log_settings = getattr(module, service.upper())
        if level:
            log_settings = update_level_in_log_config(log_settings, level)
    except AttributeError:
        message = "No logging configuration" " found for {0} in {1}".format(service, repr(module))
        logger.warning(message)
        raise KeyError(message)
    logging.config.dictConfig(log_settings)
