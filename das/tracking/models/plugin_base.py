from functools import namedtuple

import uuid
import logging

from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
from django.contrib.contenttypes.fields import GenericRelation
from core.models import TimestampedModel

import uuid

import logging
from datetime import datetime
import pytz

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField

from observations.models import Source, SourceProvider, get_default_source_provider_id
from core.models import TimestampedModel

import observations

from tracking.pubsub_registry import notify_new_tracks


logger = logging.getLogger(__name__)

class DasPluginException(Exception):
    pass

class DasPluginConfigurationError(DasPluginException):
    pass

class DasPluginConnectionError(DasPluginException):
    pass

class DasPluginFetchError(DasPluginException):
    pass


class DasPluginTransformationError(DasPluginException):
    pass


class DasPluginInsertError(DasPluginException):
    pass


logger = logging.getLogger(__name__)

class SourcePluginResult(object):
    count=0
    plugin_type=None
    source_id=None

    def to_dict(self):
        """ returns a dict of attributes of this object """
        return {
            'count': self.count,
            'plugin_type': self.plugin_type,
            'source_id': self.source_id
        }



class SourcePlugin(TimestampedModel):
    """
    This is a correlation between a Source (ex. a collar) and a Plugin (ex. SkygisticsPlugin).
    """
    STATUS_ENABLED = 'enabled'
    STATUS_DISABLED = 'disabled'

    STATUS_CHOICES = (STATUS_ENABLED, 'Enabled',
                      STATUS_DISABLED, 'Disabled'
                      )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    limits = models.Q(app_label='tracking', model='savannahplugin') | \
        models.Q(app_label='tracking', model='inreachplugin') | \
        models.Q(app_label='tracking', model='demosourceplugin') | \
        models.Q(app_label='tracking', model='awthttpplugin') | \
        models.Q(app_label='tracking', model='inreachkmlplugin') | \
        models.Q(app_label='tracking', model='skygisticssatelliteplugin') | \
        models.Q(app_label='tracking', model='firmsplugin') | \
        models.Q(app_label='tracking', model='spidertracksplugin') | \
        models.Q(app_label='tracking', model='awetelemetryplugin')

    # Generic foreign key to plugin
    plugin_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=limits)
    plugin_id = models.UUIDField()
    plugin = GenericForeignKey('plugin_type', 'plugin_id')

    source = models.ForeignKey(Source, on_delete=models.CASCADE,
                              related_name='source_plugins',
                              related_query_name='source_plugin')

    cursor_data = JSONField(null=True)
    status = models.CharField(max_length=15, default=STATUS_ENABLED)

    last_run = models.DateTimeField(auto_now_add=True, verbose_name='Timestamp for when this plugin last executed.')

    def execute(self, target=None):
        '''
        Run basic logic to fetch new observations for the associated source.
        :return:
        '''
        if self.should_run:
            result = SourcePluginResult()
            result.plugin_type = self.plugin_type
            result.source_id = self.source_id

            with target or DasDefaultTarget() as t:
                for observation in self.plugin.fetch(self.source, self.cursor_data):
                    t.send(observation)
                    result.count += 1
            self.last_run = pytz.utc.localize(datetime.utcnow())
            self.cursor_data = self.plugin.cursor_data
            self.save()

            if result.count > 0:
                notify_new_tracks(str(self.source.id))
            return result

    def maintenance(self, target=None):
        raise NotImplementedError('maintenance is not yet implemented')

    def should_run(self):
        # Defer decision to associated Plugin if possible.
        return self.plugin.should_run(self) if hasattr(self.plugin, 'should_run') else True


class TrackingPlugin(TimestampedModel):
    '''
    This is an abstract base class for Plugins that connect to a source of track data (ex. Skygistics,
    Savannah Tracking, AWT).
    '''
    STATUS_ENABLED = 'enabled'
    STATUS_DISABLED = 'disabled'

    STATUS_CHOICES = ((STATUS_ENABLED, 'Enabled'),
                      (STATUS_DISABLED, 'Disabled')
                      )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=50, null=True, unique=True, verbose_name='Unique name to identify the plugin.')
    status = models.CharField(max_length=15, default=STATUS_ENABLED, choices=STATUS_CHOICES)
    additional = JSONField(null=True)

    # A convenient relation to find the SourcePlugins that associate this Plugin.
    source_plugins = GenericRelation(SourcePlugin, content_type_field='plugin_type', object_id_field='plugin_id')

    provider = models.ForeignKey(SourceProvider, related_name='+', null=False, default=get_default_source_provider_id)

    class Meta:
        abstract = True

    @property
    def run_source_plugins(self):
        return True

    def should_run(self, source_plugin):
        return True

    def execute(self):
        '''
        By default, delegate to each SourcePlugin instance to execute.
        '''
        for sp in self.source_plugins.all():
            try:
                logger.debug('Running plugin {} for source {}'.format(sp, sp.source))
                result = sp.execute()
                if result.count > 0:
                    notify_new_tracks(result.source_id)
                logger.debug(
                    'Finished running plugin {} for source {} with result.count={}'.format(sp, sp.source, result.count))
            except DasPluginException as dpe:
                logger.exception('Running plugin {} for source {}'.format(sp, sp.source))


class PluginTarget(object):
    '''
    A contextmanager and co-routine for saving Observation data somewhere. A subclass must implement _handle_item.
    '''
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

class DasDefaultTarget(PluginTarget):
    '''
    Default target that writes to the Observations model.
    '''
    def _handle_item(self, item):
        observations.models.Observation.objects.add_observation(item)

'''
Observation Football; meant to provide a consistent way for passing essential observation data between functions.
'''
Obs = namedtuple('Obs', ('source', 'latitude', 'longitude', 'recorded_at', 'additional'))






