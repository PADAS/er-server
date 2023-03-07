from django.apps import AppConfig
from django.conf import settings

import utils.stats


class DasServerConfig(AppConfig):
    name = 'das_server'
    verbose_name = 'DAS Server'

    def ready(self):
        if settings.DISABLE_STATSD:
            utils.stats.statsd.disable_telemetry()
