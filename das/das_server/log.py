import logging
import logging.config
import sys
import traceback

try:
    # local_log.py should contain an override of DEFAULT_LOGGING as seen below
    from das_server import local_log
except ImportError:
    local_log = None

logger = logging.getLogger(__name__)

DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'syslog': {
            'format': 'mw %(levelname)s %(processName)s %(thread)d %(name)s %(message)s'
        },
        'simple': {
            'format': '%(asctime)s mw %(levelname)s %(processName)s %(thread)d %(name)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'simple'
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
            'level': 'WARNING',
        },
        '': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    }
}

WSGI = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'syslog': {
            'format': 'mw %(levelname)s %(processName)s %(thread)d %(name)s %(message)s'
        },
        'simple': {
            'format': '%(asctime)s mw %(levelname)s %(processName)s %(thread)d %(name)s %(message)s'
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/opt/python/log/das_httpd.log',
            'formatter': 'simple'
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'propagate': False,
            'level': 'INFO',
        },
        'django.request': {
            'handlers': ['file'],
            'propagate': False,
            'level': 'WARNING',
        },
        '': {
            'handlers': ['file'],
            'level': 'DEBUG',
        },
    }
}


has_initialized = False


def init_logging(service=None):
    global has_initialized
    if has_initialized:
        logger.warning('das_server logging already initialized, not loading %s /n %s',
                       service,
                       traceback.format_stack())
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
        message = 'No das_server DJANGO logging configuration' \
                  ' found for {0} in {1}'.format(service, repr(module))
        logger.warning(message)
        raise KeyError(message)
    logging.config.dictConfig(log_settings)