import logging
import logging.config
import sys

try:
    # local_log.py should contain an override of DEFAULT_LOGGING as seen below
    from . import local_log
except ImportError:
    local_log = None

logger = logging.getLogger(__name__)


DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            'format': '%(asctime)s %(levelname)s %(processName)s %(thread)d %(name)s %(message)s',
            'class': 'utils.log.CloudLogsJsonFormatter',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'json'
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'propagate': False,
            'level': 'INFO',
        },
        'django.request': {
            'handlers': ['console'],
            'propagate': False,
            'level': 'INFO',
        },
        'django.server': {
            'handlers': ['console'],
            'propagate': False,
            'level': 'INFO',
        },
        'rt_api': {
            'level': 'WARNING',
        },
        'rt_api.socketio': {
            'level': 'WARNING',
        },
        'rt_api.pubsub_listener': {
            'level': 'WARNING',
        },
        '': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
        'PIL.Image': {
            'level': 'WARNING',
        },
        'datadog.dogstatsd': {
            'level': "ERROR"
        },
    }
}


has_initialized = False


def init_logging(service=None):
    global has_initialized
    if has_initialized:
        logger.debug('logging already initialized, not loading %s',
                     service,
                     exc_info=True)
        return

    has_initialized = True

    if not service:
        service = 'default_logging'

    try:
        module = sys.modules[__name__]
        if local_log:
            module = local_log
        log_settings = getattr(module, service.upper())
    except AttributeError:
        message = 'No logging configuration' \
                  ' found for {0} in {1}'.format(service, repr(module))
        logger.warning(message)
        raise KeyError(message)
    logging.config.dictConfig(log_settings)
