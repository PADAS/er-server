import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import NamedTuple

import pytz
from dateutil.parser import parse as parse_date

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point

import observations
from core.models import TimestampedModel
from observations.models import (Source, SourceProvider,
                                 get_default_source_provider_id)
from tracking.pubsub_registry import notify_new_tracks
from utils import stats

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


class DasPluginSourceRetryError(DasPluginException):
    """Retry executing source plugin in seconds"""

    def __init__(self, retry_seconds, message=None):
        super().__init__(message)
        self.retry_seconds = retry_seconds


logger = logging.getLogger(__name__)


class SourcePluginResult(object):
    count = 0
    plugin_type = None
    source_id = None

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
        models.Q(app_label='tracking', model='spidertracksplugin') | \
        models.Q(app_label='tracking', model='awetelemetryplugin') | \
        models.Q(app_label='tracking', model='vectronicsplugin') | \
        models.Q(app_label='tracking', model='awtplugin')

    # Generic foreign key to plugin
    plugin_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, limit_choices_to=limits)
    plugin_id = models.UUIDField()
    plugin = GenericForeignKey('plugin_type', 'plugin_id')

    source = models.ForeignKey(Source, on_delete=models.CASCADE,
                               related_name='source_plugins',
                               related_query_name='source_plugin')

    cursor_data = models.JSONField(blank=True, default=dict,)
    status = models.CharField(max_length=15, default=STATUS_ENABLED)

    # last_run: datetime.min implies it hasn't ever been executed.
    last_run = models.DateTimeField(default=pytz.utc.localize(datetime(2000, 1, 1)),
                                    verbose_name='Timestamp for when this plugin last executed.')
    plugins_to_validate_location = ['awtplugin', 'skygisticssatelliteplugin']

    def execute(self, target=None):
        '''
        Run basic logic to fetch new observations for the associated source.
        :return:
        '''
        if self.should_run:

            result = SourcePluginResult()
            result.plugin_type = self.plugin_type
            result.source_id = self.source_id

            # target coroutine always returns an accumulator that indicates the number of observations that have
            # been created.
            accumulator = None
            with target or DasDefaultTarget() as t:
                for observation in self.plugin.fetch(self.source, self.cursor_data):

                    # flag observations at point (180 x 90) for selected plugins
                    if self.plugin._meta.model_name in self.plugins_to_validate_location:
                        observation = self.validate_obs_location(observation)
                    accumulator = t.send(observation)

            self.last_run = pytz.utc.localize(datetime.utcnow())
            self.cursor_data = self.plugin.cursor_data
            self.save()

            if accumulator and accumulator.get('created', 0) > 0:
                notify_new_tracks(str(self.source.id))

            stats_count = accumulator.get('created', 0) if accumulator else 0

            stats.increment("tracking", tags=[
                f"name:{self.plugin._meta.label_lower}",
                "state:created"], value=stats_count)

            return result

    def maintenance(self, target=None):
        raise NotImplementedError('maintenance is not yet implemented')

    def should_run(self):
        # Defer decision to associated Plugin if possible.
        if hasattr(self.plugin, 'should_run'):
            return self.plugin.should_run(self)
        else:
            return True

        # return self.plugin.should_run(self) if hasattr(self.plugin,
        # 'should_run') else True

    def validate_obs_location(self, observation):
        '''
        Flags observations that are at 180 x 90 as excluded_automatically.
        :param observation
        :return observation
        '''
        if (int(observation.longitude) == 180 and int(observation.latitude) == 90):
            logger.info("Invalid observation location.To be flagged/excluded")
            observation = observation._replace(
                exclusion_flags=2)  # 2 for excluded_automatically
        return observation

    def __str__(self):
        return '%s: source: %s, manufacturer_id: %s' % (self.id, self.source_id, self.source.manufacturer_id)


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
    name = models.CharField(max_length=50, null=True, unique=True,
                            verbose_name='Unique name to identify the plugin.')
    status = models.CharField(
        max_length=15, default=STATUS_ENABLED, choices=STATUS_CHOICES)
    additional = models.JSONField(blank=True, default=dict)

    provider = models.ForeignKey(
        SourceProvider, related_name='+', null=False, default=get_default_source_provider_id,
        on_delete=models.PROTECT)

    class Meta:
        abstract = True

    source_plugin_reverse_relation = None

    @property
    def run_source_plugins(self):
        return True

    def should_run(self, source_plugin):

        now = pytz.utc.localize(datetime.utcnow())

        # Don't bother running now if less than one hour has passed since the
        # latest fix.
        try:
            latest_timestamp = source_plugin.cursor_data.get(
                'latest_timestamp')
            latest_timestamp = parse_date(
                latest_timestamp) if latest_timestamp else pytz.utc.localize(datetime.min)

            # If we haven't seen data from over 30 days, then use 24 hours as
            # polling interval.
            if now - latest_timestamp > timedelta(days=30):
                wait_interval = timedelta(hours=24)
            else:
                wait_interval = self.DEFAULT_REPORT_INTERVAL

            should_run_message = {'plugin': str(self),
                                  'source': str(source_plugin.source),
                                  'wait_interval': str(wait_interval),
                                  'time_since_last': str(now - latest_timestamp),
                                  'should_run': (now - wait_interval) >= latest_timestamp
                                  }
            logger.info(json.dumps(should_run_message))

            if (now - wait_interval) >= latest_timestamp:
                return True

        except Exception:
            logger.exception(
                'Failed to determine whether source-plugin %s should run.', source_plugin)

            if (now - source_plugin.last_run) > self.DEFAULT_REPORT_INTERVAL:
                return True

        return False

    def execute(self):
        '''
        By default, delegate to each SourcePlugin instance to execute.
        '''
        for sp in self.source_plugins.all():
            try:
                logger.debug(
                    'Running plugin {} for source {}'.format(sp, sp.source))
                result = sp.execute()
                logger.debug(
                    'Finished running plugin {} for source {} with result.count={}'.format(sp, sp.source, result.count))
            except DasPluginException:
                logger.exception(
                    'Running plugin {} for source {}'.format(sp, sp.source))


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

        def func():
            accumulator = {'count': 0, 'created': 0}
            try:

                while True:
                    item = yield accumulator
                    result, created = self._handle_item(item)
                    accumulator['count'] += 1
                    accumulator['created'] += 1 if created else 0
            except GeneratorExit:
                self.logger.info("Target received %d messages, created %d items.", accumulator['count'],
                                 accumulator['created'])
            except Exception:
                self.logger.exception("Exception in plugin handler.")

        r = func()
        next(r)
        self._r = r
        return r

    def __enter__(self):
        return self._start()

    def __exit__(self, ex_type, exc_value, tb):

        if ex_type not in [None, DasPluginSourceRetryError]:
            self.logger.info("Exiting with Exception. %s %s", ex_type, exc_value,
                             exc_info=(ex_type, exc_value, tb))

        self._r.close()
        if ex_type == DasPluginSourceRetryError:
            return False
        return True


class DasDefaultTarget(PluginTarget):
    '''
    Default target that writes to the Observations model.
    '''

    def _handle_item(self, item):

        location = Point(x=item.longitude, y=item.latitude)
        additional = item.additional or {}
        result, created = observations.models.Observation.objects. \
            get_or_create(
                source_id=item.source.id,
                recorded_at=item.recorded_at,
                defaults=dict(
                    location=location,
                    additional=additional,
                    exclusion_flags=item.exclusion_flags
                )
            )

        return result, created


class DasFireEventTarget(PluginTarget):
    '''
    FIRMS target.
    '''

    def _handle_item(self, item):

        location = Point(x=item.longitude, y=item.latitude)
        additional = item.additional or {}
        result, created = observations.models.Observation.objects.get_or_create(source_id=item.source.id,
                                                                                recorded_at=item.recorded_at,
                                                                                defaults=dict(
                                                                                    location=location,
                                                                                    additional=additional
                                                                                ))
        return result, created


class Obs(NamedTuple):
    """
    Represents the payload sent to create a new observation
    """
    source: Source
    latitude: float
    longitude: float
    recorded_at: datetime
    additional: dict = {}
    exclusion_flags: int = 0
