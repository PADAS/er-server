import logging

from django.contrib.gis.db import models

from observations.models import Subject

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

    subject = models.ForeignKey(to=Subject, on_delete=models.CASCADE)

    # At least one Analyzer shouldn't report back when changing back to 'good' state
    is_two_state = True

    class Meta:
        abstract = True

    @property
    def valid_times(self):
        return (self.min_time, self.max_time)

    @property
    def name(self):
        return self.__class__.__name__

    def analyze(self, track):
        logger.info('{} analyzing {} records'.format(self.__class__.__name__, len(track)))


class AnalyzerResult():

    level = NOMINAL
    value = 0.0
    title = 'AnalyzerResult'
    location = None

    def __init__(self, analyzer):
        self.analyzer = analyzer

    def to_dict(self):
        """ returns a dict of attributes of this object """

        return {
            'title': self.title,
            'level': self.level,
            'value': self.value,
            'analyzer_type': self.analyzer.name,
            'location': self.location and str(self.location) or None
        }
