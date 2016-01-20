from datetime import timedelta
import inspect
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
        return self._valid_times or (self.min_time, self.max_time)

    def analyze(self, track):
        logger.info('{} analyzing'.format(self.__class__.__name__))

    def truncate_track(self, track, hours=24):
        """ truncates track to most recent hours of observations """
        t_last_observation, p_last_observation  = track.last_observation
        t_cutoff = t_last_observation - timedelta(hours=24)
        return track.truncate(before=t_cutoff)

class AnalyzerResult():
    level = NOMINAL
    value = 0.0
    analyzer_type = None

    def to_dict(self):
        """ returns a dict of non-hidden attributes of this object """

        # there must be a better way..
        return {x:y for x,y in inspect.getmembers(self) if not x.startswith('__') and x != 'to_dict'}

