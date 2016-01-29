from datetime import timedelta
import inspect
from functools import namedtuple
from abc import ABCMeta, abstractmethod

import uuid
import logging

from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
from core.models import TimestampedModel

import observations

logger = logging.getLogger(__name__)

class DasPluginConfigurationError(Exception):
    pass


class DasPluginFetchError(Exception):
    pass


class DasPluginTransformationError(Exception):
    pass


class DasPluginInsertError(Exception):
    pass


class Plugin(TimestampedModel):

    STATUS_ENABLED = 'enabled'
    STATUS_DISABLED = 'disabled'

    STATUS_CHOICES = ((STATUS_ENABLED, 'Enabled'),
                      (STATUS_DISABLED, 'Disabled')
                      )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    min_time = models.TimeField(null=True)
    max_time = models.TimeField(null=True)
    status = models.CharField(max_length=15, default=STATUS_ENABLED, choices=STATUS_CHOICES)
    additional = JSONField(null=True)

    class Meta:
        abstract = True



class PluginTarget(object):
    def __init__(self, config=None):
        self.__config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def _handle_item(self, item):
        '''
        Subclass must implement _handle_item.
        :param item:
        :return:
        '''
        raise NotImplementedError('Subclasses must implement _handle_item')

    def _start(self):
        '''
        Subclass may implement _start.
        :return: coroutine with wraps _handle_item.
        '''

        def _():
            cnt = 0
            try:
                while True:
                    item = (yield)
                    self._handle_item(item)
                    cnt += 1
            except GeneratorExit:
                self.logger.info("Target received %d messages", cnt)
            except Exception as e:
                self.logger.exception("Exception in plugin handler.")

        r = _()
        next(r)
        self._r = r
        return r

    def __enter__(self):
        return self._start()

    def __exit__(self, ex_type, exc_value, traceback):
        self.logger.debug("Exiting. %s %s %s", ex_type, exc_value, traceback)
        self._r.close()
        return True

'''
Default Classes
'''
class DasDefaultTarget(PluginTarget):

    def _handle_item(self, item):
        observations.models.Observation.objects.add_observation(item)

'''
Observation Football
'''
Obs = namedtuple('Obs', ('source', 'latitude', 'longitude', 'recorded_at', 'additional'))






