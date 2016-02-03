import logging

from django.contrib.gis.db import models


logger = logging.getLogger(__name__)

# borrow levels from logging:

NOMINAL = 20
INFO = 20
WARNING = 30
ERROR = 40
CRITICAL = 50


class Analyzer(models.Model):
    min_time = models.TimeField(null=True)
    max_time = models.TimeField(null=True)

    class Meta:
        abstract = True

    @property
    def valid_times(self):
        return (self.min_time, self.max_time)

    def analyze(self, track):
        logger.info('{} analyzing {} records'.format(self.__class__.__name__, len(track)))


class AnalyzerResult():
    level = NOMINAL
    value = 0.0
    analyzer_type = None
    location = None

    def to_dict(self):
        """ returns a dict of attributes of this object """

        return {
            'level': self.level,
            'value': self.value,
            'analyzer_type': self.analyzer_type,
            'location': self.location and str(self.location) or None
        }

